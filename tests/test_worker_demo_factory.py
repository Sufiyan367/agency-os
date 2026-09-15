import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.database.connection import Base
from app.database.models import (
    Business, CustomerProject, ProjectStatus, PipelineStage,
    ProjectSpecification, DesignSpecification, AIFeatureSpecification,
    ProjectBuild, BuildQA, ProjectDeployment
)
from app.orchestrator.worker import PersistentAgencyWorker


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_drains_demo_backlog_from_demo_requested_business(test_db):
    """
    Validates that PersistentAgencyWorker picks up a Business in DEMO_REQUESTED state,
    creates the CustomerProject, runs the complete pipeline (spec -> design -> prototype -> build -> qa -> deploy),
    and marks it DEMO_READY.
    """
    biz = Business(
        name="Apex Commercial Roofing",
        domain="apexroofing.com",
        niche="Roofing",
        city="Austin",
        country="US",
        pipeline_stage=PipelineStage.DEMO_REQUESTED.value
    )
    test_db.add(biz)
    await test_db.commit()
    await test_db.refresh(biz)

    worker = PersistentAgencyWorker()
    count = await worker.drain_demo_backlog(test_db, limit=5)
    assert count == 1

    # Verify CustomerProject was created and reached DEMO_READY
    proj_stmt = select(CustomerProject).where(CustomerProject.business_id == biz.id)
    proj = (await test_db.execute(proj_stmt)).scalars().first()
    assert proj is not None
    assert proj.status == ProjectStatus.DEMO_READY.value
    assert proj.current_stage == "DEMO_READY"

    # Verify artifacts and specs created
    spec_stmt = select(ProjectSpecification).where(ProjectSpecification.project_id == proj.id)
    spec = (await test_db.execute(spec_stmt)).scalars().first()
    assert spec is not None
    assert spec.is_canonical is True

    deploy_stmt = select(ProjectDeployment).where(ProjectDeployment.project_id == proj.id)
    deployment = (await test_db.execute(deploy_stmt)).scalars().first()
    assert deployment is not None
    assert "/demo/apex-commercial-roofing/" in deployment.deployment_url

    # Idempotency check: running again should not process already-completed project
    count_again = await worker.drain_demo_backlog(test_db, limit=5)
    assert count_again == 0


@pytest.mark.asyncio
async def test_worker_drains_existing_demo_requested_customer_project(test_db):
    """
    Validates that a CustomerProject explicitly created in DEMO_REQUESTED state
    is picked up and completed by the worker.
    """
    biz = Business(
        name="Lone Star Dental Group",
        domain="lonestardental.com",
        niche="Dental",
        city="Dallas",
        country="US",
        pipeline_stage=PipelineStage.DEMO_REQUESTED.value
    )
    test_db.add(biz)
    await test_db.commit()
    await test_db.refresh(biz)

    proj = CustomerProject(
        project_id="proj_lone-star-dental_101",
        business_id=biz.id,
        customer_slug="lone-star-dental",
        title="Lone Star Dental Group",
        industry="Dental",
        status=ProjectStatus.DEMO_REQUESTED.value,
        current_stage="DEMO_REQUESTED"
    )
    test_db.add(proj)
    await test_db.commit()

    worker = PersistentAgencyWorker()
    count = await worker.drain_demo_backlog(test_db, limit=5)
    assert count == 1

    await test_db.refresh(proj)
    assert proj.status == ProjectStatus.DEMO_READY.value
    assert proj.current_stage == "DEMO_READY"
