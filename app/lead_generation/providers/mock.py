from typing import List
from app.lead_generation.providers.base import BaseLeadDiscoveryProvider
from app.lead_generation.targeting import TargetingConfig
from app.lead_generation.schemas import NormalizedBusinessRecord

class MockLeadDiscoveryProvider(BaseLeadDiscoveryProvider):
    """
    High-fidelity Mock Lead Discovery Provider enriched with observable signals
    for evaluating commercial purchasing capacity ($1,000+ services) and digital opportunity.
    """

    @property
    def provider_name(self) -> str:
        return "mock_directory"

    async def discover_businesses(self, targeting: TargetingConfig) -> List[NormalizedBusinessRecord]:
        results: List[NormalizedBusinessRecord] = []
        region = targeting.regions[0] if targeting.regions else "Texas"
        country = targeting.country

        # Detailed blueprints per city with observable scale and technical signals
        # (name, address, website, phone, rating, reviews, num_loc, years, comm_res, fleet, emerg, financing, hiring, affluent, speed_issue, seo_issue, mobile_issue, lead_capture_issue)
        city_blueprints = {
            "Austin": [
                # 1. High Buyer + High Opp -> Priority Prospect
                ("Lone Star Heating & Air Conditioning", "10404 Metric Blvd, Austin, TX", "https://lonestarhvac-austin.example.com", "(512) 555-0144", 4.8, 142, 2, 14, True, True, True, True, True, True, True, True, True, True),
                # 2. High Buyer + High Opp -> Priority Prospect
                ("Capital City Climate Pros", "2201 E 51st St, Austin, TX", "https://capitalcityclimate.example.com", "(512) 555-0219", 4.6, 89, 2, 9, True, True, True, True, True, False, True, True, True, False),
                # 3. High Buyer + Low Opp -> Nurture (Great business, but fast website)
                ("Barton Springs AC & Heating", "1401 S Lamar Blvd, Austin, TX", "https://bartonspringshvac.example.com", "(512) 555-0377", 4.9, 215, 3, 20, True, True, True, True, False, True, False, False, False, False),
                # 4. Low Buyer + High Opp -> Low Value (Solo technician, slow website)
                ("Hill Country Comfort Masters", "8200 Brodie Ln, Austin, TX", "https://hillcountrycomfort.example.com", "(512) 555-0482", 4.2, 18, 1, 2, False, False, False, False, False, False, True, True, True, True),
                # 5. High Buyer + High Opp -> Priority Prospect
                ("Austin Express Heating & Cooling", "9300 Research Blvd, Austin, TX", "https://austinexpressair.example.com", "(512) 555-0551", 4.7, 112, 2, 11, True, True, True, True, True, True, True, True, False, True),
                # 6. Moderate Buyer + Moderate Opp -> Nurture
                ("South Congress Air Solutions", "3800 S Congress Ave, Austin, TX", "https://socohvac.example.com", "(512) 555-0628", 4.5, 67, 1, 6, False, True, True, False, False, True, True, False, True, False),
                # 7. Discard candidate (No phone, no email, bad rating)
                ("Unresponsive Travis Cooling", "500 Airport Blvd, Austin, TX", "https://unresponsivetravis.example.com", None, 2.8, 4, 1, 1, False, False, False, False, False, False, True, True, True, True),
                # 8. High Buyer + High Opp -> Priority Prospect
                ("Round Rock & Austin Air Doctor", "3100 E Rundberg Ln, Austin, TX", "https://austinairdoctor.example.com", "(512) 555-0899", 4.8, 178, 2, 15, True, True, True, True, True, False, True, True, True, True),
                # 9. Low Buyer + Low Opp -> Low Value
                ("Travis County Thermal Systems", "4500 Manchaca Rd, Austin, TX", "https://travisclimate.example.com", "(512) 555-0922", 3.9, 12, 1, 3, False, False, False, False, False, False, False, False, False, False),
                # 10. High Buyer + High Opp -> Priority Prospect
                ("Red River Mechanical HVAC", "1200 E 7th St, Austin, TX", "https://redrivermechanical.example.com", "(512) 555-1033", 4.6, 94, 2, 8, True, True, True, True, True, True, True, True, True, False),
                # 11. High Buyer + Low Opp -> Nurture
                ("Zilker Park Air Conditioning", "2100 Barton Springs Rd, Austin, TX", "https://zilkerac.example.com", "(512) 555-1155", 4.7, 130, 2, 12, True, True, True, True, False, True, False, False, False, False),
                # 12. High Buyer + High Opp -> Priority Prospect
                ("East Austin Furnace & AC", "1900 E 12th St, Austin, TX", "https://eastaustinhvac.example.com", "(512) 555-1288", 4.4, 52, 1, 7, True, True, True, True, True, False, True, True, True, True),
                # 13. High Buyer + High Opp -> Priority Prospect
                ("Lake Travis Air Specialists", "620 N FM 620, Austin, TX", "https://laketravisair.example.com", "(512) 555-1477", 4.9, 260, 3, 22, True, True, True, True, True, True, True, True, True, True),
                # 14. Moderate Buyer + High Opp -> Nurture
                ("Mueller Climate Group", "4200 Mueller Blvd, Austin, TX", "https://muellerclimate.example.com", "(512) 555-1566", 4.5, 78, 1, 5, False, True, True, False, False, True, True, True, False, True),
                # 15. High Buyer + High Opp -> Priority Prospect
                ("Allandale AC & Heating", "5600 Burnet Rd, Austin, TX", "https://allandaleac.example.com", "(512) 555-1711", 4.7, 105, 2, 10, True, True, True, True, True, True, True, True, True, True),
            ],
            "Dallas": [
                # 1. High Buyer + High Opp -> Priority
                ("Metroplex Precision Air & Heat", "1500 Marilla St, Dallas, TX", "https://metroplexair.example.com", "(214) 555-0133", 4.8, 195, 3, 18, True, True, True, True, True, True, True, True, True, True),
                # 2. High Buyer + High Opp -> Priority
                ("Trinity River HVAC Specialists", "3200 Continental Ave, Dallas, TX", "https://trinityriverhvac.example.com", "(214) 555-0244", 4.6, 82, 2, 7, True, True, True, True, True, False, True, True, True, False),
                # 3. High Buyer + Low Opp -> Nurture
                ("Big D Climate Solutions", "4100 Harry Hines Blvd, Dallas, TX", "https://bigdclimate.example.com", "(214) 555-0355", 4.9, 310, 4, 25, True, True, True, True, False, True, False, False, False, False),
                # 4. High Buyer + High Opp -> Priority
                ("North Dallas Heating & Air", "12800 Preston Rd, Dallas, TX", "https://northdallashvac.example.com", "(214) 555-0466", 4.7, 140, 2, 12, True, True, True, True, True, True, True, True, True, True),
                # 5. Low Buyer + High Opp -> Low Value (Solo installer)
                ("Oak Cliff AC & Mechanical", "700 N Zang Blvd, Dallas, TX", "https://oakcliffhvac.example.com", "(214) 555-0577", 4.3, 14, 1, 2, False, False, False, False, False, False, True, True, True, True),
                # 6. High Buyer + High Opp -> Priority
                ("Highland Park Thermal Care", "4200 Mockingbird Ln, Dallas, TX", "https://highlandparkclimate.example.com", "(214) 555-0799", 4.9, 220, 2, 16, True, True, True, True, True, True, True, True, True, True),
                # 7. High Buyer + High Opp -> Priority
                ("Preston Hollow Climate Group", "10700 Preston Rd, Dallas, TX", "https://prestonhollowhvac.example.com", "(214) 555-1044", 4.8, 180, 2, 14, True, True, True, True, True, True, True, True, True, True),
                # 8. High Buyer + Low Opp -> Nurture
                ("Uptown Dallas AC Masters", "2600 McKinney Ave, Dallas, TX", "https://uptownacmasters.example.com", "(214) 555-0933", 4.6, 95, 2, 8, True, True, True, True, False, True, False, False, False, False),
                # 9. High Buyer + High Opp -> Priority
                ("Design District HVAC Pros", "1400 Dragon St, Dallas, TX", "https://designdistrictair.example.com", "(214) 555-1322", 4.7, 115, 2, 10, True, True, True, True, True, False, True, True, True, True),
                # 10. High Buyer + High Opp -> Priority
                ("Love Field Commercial HVAC", "7300 Cedar Springs Rd, Dallas, TX", "https://lovefieldhvac.example.com", "(214) 555-1699", 4.8, 160, 3, 20, True, True, True, True, True, True, True, True, True, True),
            ],
            "Houston": [
                # 1. High Buyer + High Opp -> Priority
                ("Space City Heating & Cooling", "900 Bagby St, Houston, TX", "https://spacecityair.example.com", "(713) 555-0122", 4.8, 280, 3, 19, True, True, True, True, True, True, True, True, True, True),
                # 2. High Buyer + High Opp -> Priority
                ("Bayou City HVAC Solutions", "2400 Allen Pkwy, Houston, TX", "https://bayoucityhvac.example.com", "(713) 555-0233", 4.7, 165, 2, 11, True, True, True, True, True, False, True, True, True, True),
                # 3. High Buyer + Low Opp -> Nurture
                ("Energy Corridor Climate Pros", "14700 Memorial Dr, Houston, TX", "https://energycorridorclimate.example.com", "(713) 555-0344", 4.9, 320, 4, 24, True, True, True, True, False, True, False, False, False, False),
                # 4. High Buyer + High Opp -> Priority
                ("Heights Air Conditioning & Heat", "1500 Heights Blvd, Houston, TX", "https://heightsair.example.com", "(713) 555-0455", 4.6, 110, 2, 9, True, True, True, True, True, True, True, True, True, True),
                # 5. High Buyer + High Opp -> Priority
                ("Galleria Area Heating & Air", "5085 Westheimer Rd, Houston, TX", "https://galleriahvac.example.com", "(713) 555-0677", 4.8, 210, 2, 15, True, True, True, True, True, True, True, True, True, True),
                # 6. High Buyer + High Opp -> Priority
                ("River Oaks Climate Group", "2000 Westheimer Rd, Houston, TX", "https://riveroakshvac.example.com", "(713) 555-0911", 4.9, 340, 3, 26, True, True, True, True, True, True, True, True, True, True),
                # 7. Low Buyer + High Opp -> Low Value (Solo installer)
                ("Southwest Houston Handyman AC", "9800 Bissonnet St, Houston, TX", "https://southwesthoustonair.example.com", "(713) 555-1511", 4.2, 10, 1, 1, False, False, False, False, False, False, True, True, True, True),
                # 8. High Buyer + High Opp -> Priority
                ("Sugar Land & Houston Air Masters", "12000 Southwest Fwy, Houston, TX", "https://sugarlandhoustonair.example.com", "(713) 555-1633", 4.7, 150, 2, 13, True, True, True, True, True, True, True, True, True, True),
                # 9. High Buyer + High Opp -> Priority
                ("Katy & West Houston HVAC", "18000 Park Row, Houston, TX", "https://katyhoustonhvac.example.com", "(713) 555-1755", 4.6, 118, 2, 8, True, True, True, True, True, False, True, True, True, True),
            ]
        }

        for city in targeting.cities:
            blueprints = city_blueprints.get(city, [])
            for (
                name, addr, web, ph, rat, rev,
                locs, yrs, comm, fleet, emerg, fin, hire, affl,
                spd_err, seo_err, mob_err, lead_err
            ) in blueprints:
                results.append(
                    NormalizedBusinessRecord(
                        business_name=name,
                        category="HVAC Contractor",
                        address=addr,
                        city=city,
                        region=region,
                        country=country,
                        website=web,
                        phone=ph,
                        email=f"contact@{web.replace('https://', '').replace('/', '')}" if web else None,
                        rating=rat,
                        review_count=rev,
                        source=self.provider_name,
                        source_url=f"{web}/contact" if web else None,
                        num_locations=locs,
                        years_in_business=yrs,
                        is_commercial_and_residential=comm,
                        has_fleet_or_technicians=fleet,
                        offers_emergency_service=emerg,
                        authorized_dealer_or_financing=fin,
                        hiring_active=hire,
                        affluent_service_area=affl,
                        page_speed_issue=spd_err,
                        seo_issue=seo_err,
                        mobile_ux_issue=mob_err,
                        lacks_lead_capture=lead_err
                    )
                )

        # ----------------------------------------------------------------------
        # INJECT INTENTIONAL DUPLICATES TO EXERCISE DEDUPLICATION ENGINE
        # ----------------------------------------------------------------------
        # 1. Exact same website URL
        results.append(
            NormalizedBusinessRecord(
                business_name="Lone Star Heating & AC (Duplicate Domain)",
                category="HVAC Contractor",
                city="Austin",
                region=region,
                country=country,
                website="http://www.lonestarhvac-austin.example.com/",
                phone="(512) 555-9999",
                rating=4.7,
                review_count=50,
                source=self.provider_name
            )
        )
        # 2. Same Phone Number
        results.append(
            NormalizedBusinessRecord(
                business_name="Capital City 24hr Emergency Air",
                category="HVAC Contractor",
                city="Austin",
                region=region,
                country=country,
                website="https://capitalcityemergency.example.com",
                phone="+1 512-555-0219", # Duplicate phone of Capital City Climate Pros
                rating=4.5,
                review_count=30,
                source=self.provider_name
            )
        )
        # 3. Same Name in same city
        results.append(
            NormalizedBusinessRecord(
                business_name="Barton Springs AC & Heating",
                category="HVAC Contractor",
                city="Austin",
                region=region,
                country=country,
                website="https://bartonsprings-mirror.example.com",
                phone="(512) 555-8888",
                rating=4.9,
                review_count=190,
                source=self.provider_name
            )
        )

        return results
