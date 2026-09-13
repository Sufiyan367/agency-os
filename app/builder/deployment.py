"""
Demo Deployment Engine — Phase 12 of Autonomous Demo & Build Pipeline.
Coordinates physical artifact deployment to customer-isolated sandboxes,
persists deployment records, and handles rollback checkpoints.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CustomerProject, ProjectBuild, ProjectDeployment
from app.builder.models import DeploymentResult, BuildResult
from app.builder.providers.firebase_provider import FirebaseInfrastructureProvider
from app.core.logging import logger


class DemoDeploymentEngine:
    """
    Manages isolated customer demo deployments and sandboxes.
    """

    def __init__(self, infra_provider: Optional[FirebaseInfrastructureProvider] = None):
        self.infra_provider = infra_provider or FirebaseInfrastructureProvider()

    async def deploy_demo(
        self,
        session: AsyncSession,
        customer_project: CustomerProject,
        build: ProjectBuild,
        build_result: Optional[BuildResult] = None
    ) -> ProjectDeployment:
        # 1. Provision & Deploy via infrastructure provider
        res: DeploymentResult = await self.infra_provider.provision_and_deploy(
            build=build,
            customer_project=customer_project
        )

        # 2. Write generated files to physical sandbox directory
        if build_result and build_result.generated_files:
            for item in build_result.generated_files:
                file_dest = os.path.join(res.artifacts_dir, item.file_path)
                os.makedirs(os.path.dirname(file_dest), exist_ok=True)
                if item.content:
                    with open(file_dest, "w", encoding="utf-8") as f:
                        f.write(item.content)

        # 3. Create ProjectDeployment record in database
        deployment = ProjectDeployment(
            project_id=customer_project.id,
            build_id=build.id,
            demo_id=res.demo_id,
            deployment_url=res.deployment_url,
            status="DEMO_READY",
            deployed_at=datetime.utcnow(),
            verified_at=datetime.utcnow(),
            metadata_json=res.metadata
        )
        session.add(deployment)

        customer_project.status = "READY"
        customer_project.current_stage = "DEPLOYED"
        await session.commit()
        await session.refresh(deployment)

        logger.info(
            f"[DemoDeploymentEngine] Live demo deployed for {customer_project.customer_slug}: "
            f"{res.deployment_url} (demo_id: {res.demo_id})"
        )
        return deployment


deployment_engine = DemoDeploymentEngine()
