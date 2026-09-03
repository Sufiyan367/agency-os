from typing import List
from app.lead_generation.providers.base import BaseLeadDiscoveryProvider
from app.lead_generation.targeting import TargetingConfig
from app.lead_generation.schemas import NormalizedBusinessRecord

class MockLeadDiscoveryProvider(BaseLeadDiscoveryProvider):
    """
    High-fidelity Mock Lead Discovery Provider.
    Generates realistic SMB records matching configured regions, cities, and niches.
    Includes intentional duplicates and non-matching records to rigorously test
    deduplication and validation filters.
    """

    @property
    def provider_name(self) -> str:
        return "mock_directory"

    async def discover_businesses(self, targeting: TargetingConfig) -> List[NormalizedBusinessRecord]:
        results: List[NormalizedBusinessRecord] = []
        region = targeting.regions[0] if targeting.regions else "Texas"
        country = targeting.country

        # Seed data templates per city
        city_blueprints = {
            "Austin": [
                ("Lone Star Heating & Air Conditioning", "10404 Metric Blvd, Austin, TX 78758", "https://lonestarhvac-austin.example.com", "(512) 555-0144", 4.8, 142),
                ("Capital City Climate Pros", "2201 E 51st St, Austin, TX 78723", "https://capitalcityclimate.example.com", "(512) 555-0219", 4.6, 89),
                ("Barton Springs AC & Heating", "1401 S Lamar Blvd, Austin, TX 78704", "https://bartonspringshvac.example.com", "(512) 555-0377", 4.9, 215),
                ("Hill Country Comfort Masters", "8200 Brodie Ln, Austin, TX 78745", "https://hillcountrycomfort.example.com", "(512) 555-0482", 4.2, 34),
                ("Austin Express Heating & Cooling", "9300 Research Blvd, Austin, TX 78759", "https://austinexpressair.example.com", "(512) 555-0551", 4.7, 112),
                ("South Congress Air Solutions", "3800 S Congress Ave, Austin, TX 78704", "https://socohvac.example.com", "(512) 555-0628", 4.5, 67),
                ("Cedar Park & Austin HVAC Pros", "11000 N Mopac Expy, Austin, TX 78759", "https://cedarparkaustinhvac.example.com", "(512) 555-0713", 4.3, 45),
                ("Round Rock & Austin Air Doctor", "3100 E Rundberg Ln, Austin, TX 78753", "https://austinairdoctor.example.com", "(512) 555-0899", 4.8, 178),
                ("Travis County Thermal Systems", "4500 Manchaca Rd, Austin, TX 78745", "https://travisclimate.example.com", "(512) 555-0922", 3.9, 18),
                ("Red River Mechanical HVAC", "1200 E 7th St, Austin, TX 78702", "https://redrivermechanical.example.com", "(512) 555-1033", 4.6, 94),
                ("Zilker Park Air Conditioning", "2100 Barton Springs Rd, Austin, TX 78704", "https://zilkerac.example.com", "(512) 555-1155", 4.7, 130),
                ("East Austin Furnace & AC", "1900 E 12th St, Austin, TX 78702", "https://eastaustinhvac.example.com", "(512) 555-1288", 4.4, 52),
                ("North Loop Cooling Services", "5300 Airport Blvd, Austin, TX 78751", "https://northloopair.example.com", "(512) 555-1399", 4.1, 29),
                ("Lake Travis Air Specialists", "620 N FM 620, Austin, TX 78734", "https://laketravisair.example.com", "(512) 555-1477", 4.9, 260),
                ("Mueller Climate Group", "4200 Mueller Blvd, Austin, TX 78723", "https://muellerclimate.example.com", "(512) 555-1566", 4.5, 78),
                ("Oak Hill Heating & Air", "6705 W Hwy 290, Austin, TX 78735", "https://oakhillhvac.example.com", "(512) 555-1644", 4.3, 41),
                ("Allandale AC & Heating", "5600 Burnet Rd, Austin, TX 78756", "https://allandaleac.example.com", "(512) 555-1711", 4.7, 105),
            ],
            "Dallas": [
                ("Metroplex Precision Air & Heat", "1500 Marilla St, Dallas, TX 75201", "https://metroplexair.example.com", "(214) 555-0133", 4.8, 195),
                ("Trinity River HVAC Specialists", "3200 Continental Ave, Dallas, TX 75207", "https://trinityriverhvac.example.com", "(214) 555-0244", 4.6, 82),
                ("Big D Climate Solutions", "4100 Harry Hines Blvd, Dallas, TX 75219", "https://bigdclimate.example.com", "(214) 555-0355", 4.9, 310),
                ("North Dallas Heating & Air", "12800 Preston Rd, Dallas, TX 75230", "https://northdallashvac.example.com", "(214) 555-0466", 4.7, 140),
                ("Oak Cliff AC & Mechanical", "700 N Zang Blvd, Dallas, TX 75208", "https://oakcliffhvac.example.com", "(214) 555-0577", 4.3, 61),
                ("White Rock Air Pros", "9100 Garland Rd, Dallas, TX 75218", "https://whiterockair.example.com", "(214) 555-0688", 4.5, 73),
                ("Highland Park Thermal Care", "4200 Mockingbird Ln, Dallas, TX 75205", "https://highlandparkclimate.example.com", "(214) 555-0799", 4.9, 220),
                ("Deep Ellum Heating & Cooling", "2800 Main St, Dallas, TX 75226", "https://deepellumair.example.com", "(214) 555-0811", 4.2, 38),
                ("Uptown Dallas AC Masters", "2600 McKinney Ave, Dallas, TX 75204", "https://uptownacmasters.example.com", "(214) 555-0933", 4.6, 95),
                ("Preston Hollow Climate Group", "10700 Preston Rd, Dallas, TX 75230", "https://prestonhollowhvac.example.com", "(214) 555-1044", 4.8, 180),
                ("Bishop Arts Air Solutions", "400 N Bishop Ave, Dallas, TX 75208", "https://bishopartsair.example.com", "(214) 555-1177", 4.4, 54),
                ("Knox-Henderson Heating & Air", "3100 Knox St, Dallas, TX 75205", "https://knoxhendersonhvac.example.com", "(214) 555-1299", 4.5, 68),
                ("Design District HVAC Pros", "1400 Dragon St, Dallas, TX 75207", "https://designdistrictair.example.com", "(214) 555-1322", 4.7, 115),
                ("Lake Highlands Air Care", "9600 Audelia Rd, Dallas, TX 75238", "https://lakehighlandsair.example.com", "(214) 555-1455", 4.3, 47),
                ("Downtown Dallas Express Air", "1900 Elm St, Dallas, TX 75201", "https://downtowndallasair.example.com", "(214) 555-1588", 4.6, 88),
                ("Love Field Commercial HVAC", "7300 Cedar Springs Rd, Dallas, TX 75235", "https://lovefieldhvac.example.com", "(214) 555-1699", 4.8, 160),
            ],
            "Houston": [
                ("Space City Heating & Cooling", "900 Bagby St, Houston, TX 77002", "https://spacecityair.example.com", "(713) 555-0122", 4.8, 280),
                ("Bayou City HVAC Solutions", "2400 Allen Pkwy, Houston, TX 77019", "https://bayoucityhvac.example.com", "(713) 555-0233", 4.7, 165),
                ("Energy Corridor Climate Pros", "14700 Memorial Dr, Houston, TX 77079", "https://energycorridorclimate.example.com", "(713) 555-0344", 4.9, 320),
                ("Heights Air Conditioning & Heat", "1500 Heights Blvd, Houston, TX 77008", "https://heightsair.example.com", "(713) 555-0455", 4.6, 110),
                ("Montrose Thermal Masters", "1200 Westheimer Rd, Houston, TX 77006", "https://montroseclimate.example.com", "(713) 555-0566", 4.5, 75),
                ("Galleria Area Heating & Air", "5085 Westheimer Rd, Houston, TX 77056", "https://galleriahvac.example.com", "(713) 555-0677", 4.8, 210),
                ("Memorial Heating & Air Care", "9500 Katy Fwy, Houston, TX 77024", "https://memorialaircare.example.com", "(713) 555-0788", 4.9, 295),
                ("Midtown Houston AC Specialists", "2600 Travis St, Houston, TX 77006", "https://midtownhoustonair.example.com", "(713) 555-0899", 4.3, 58),
                ("River Oaks Climate Group", "2000 Westheimer Rd, Houston, TX 77098", "https://riveroakshvac.example.com", "(713) 555-0911", 4.9, 340),
                ("Clear Lake & Bay HVAC", "16600 Space Center Blvd, Houston, TX 77058", "https://clearlakebayair.example.com", "(713) 555-1022", 4.6, 92),
                ("Rice Village Air Solutions", "2500 University Blvd, Houston, TX 77005", "https://ricevillageair.example.com", "(713) 555-1144", 4.7, 125),
                ("Westchase Climate Control", "2800 Gessner Rd, Houston, TX 77080", "https://westchaseair.example.com", "(713) 555-1266", 4.4, 63),
                ("Northwest Houston AC Pros", "11000 Northwest Fwy, Houston, TX 77092", "https://northwesthoustonhvac.example.com", "(713) 555-1388", 4.5, 84),
                ("Cypress Creek Thermal Care", "15000 Cypress Creek Pkwy, Houston, TX 77070", "https://cypresscreekair.example.com", "(713) 555-1499", 4.8, 175),
                ("Southwest Houston Heating & Air", "9800 Bissonnet St, Houston, TX 77036", "https://southwesthoustonair.example.com", "(713) 555-1511", 4.2, 44),
                ("Sugar Land & Houston Air Masters", "12000 Southwest Fwy, Houston, TX 77074", "https://sugarlandhoustonair.example.com", "(713) 555-1633", 4.7, 150),
                ("Katy & West Houston HVAC", "18000 Park Row, Houston, TX 77084", "https://katyhoustonhvac.example.com", "(713) 555-1755", 4.6, 118),
            ]
        }

        # Build raw candidate records
        for city in targeting.cities:
            blueprints = city_blueprints.get(city, [])
            for name, address, website, phone, rating, reviews in blueprints:
                results.append(
                    NormalizedBusinessRecord(
                        business_name=name,
                        category="HVAC Contractor",
                        address=address,
                        city=city,
                        region=region,
                        country=country,
                        website=website,
                        phone=phone,
                        rating=rating,
                        review_count=reviews,
                        source=self.provider_name,
                        source_url=f"{website}/contact"
                    )
                )

        # ----------------------------------------------------------------------
        # INJECT INTENTIONAL DUPLICATES TO EXERCISE DEDUPLICATION ENGINE
        # ----------------------------------------------------------------------
        # 1. Exact same website URL (slightly different protocol/case)
        results.append(
            NormalizedBusinessRecord(
                business_name="Lone Star Heating and AC (Duplicate Web)",
                category="HVAC Contractor",
                address="10404 Metric Blvd Suite B, Austin, TX",
                city="Austin",
                region=region,
                country=country,
                website="http://www.lonestarhvac-austin.example.com/", # Same domain
                phone="(512) 555-9999",
                rating=4.7,
                review_count=50,
                source=self.provider_name
            )
        )

        # 2. Same Phone Number (different formatting)
        results.append(
            NormalizedBusinessRecord(
                business_name="Capital City Emergency AC",
                category="HVAC Contractor",
                address="2201 E 51st St, Austin, TX",
                city="Austin",
                region=region,
                country=country,
                website="https://capitalcityemergency.example.com",
                phone="+15125550219", # Same phone as Capital City Climate Pros
                rating=4.5,
                review_count=30,
                source=self.provider_name
            )
        )

        # 3. Exact Duplicate Business Name in the same city
        results.append(
            NormalizedBusinessRecord(
                business_name="Barton Springs AC & Heating", # Duplicate name
                category="HVAC Contractor",
                address="1401 South Lamar Boulevard, Austin, TX",
                city="Austin",
                region=region,
                country=country,
                website="https://bartonsprings-alt.example.com",
                phone="(512) 555-8888",
                rating=4.9,
                review_count=190,
                source=self.provider_name
            )
        )

        return results
