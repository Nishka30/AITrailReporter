"""location category taxonomy: multi-category classification for places

Adds TrailMind's controlled category vocabulary (`location_categories`) and the
many-to-many assignment of those categories to places
(`location_category_assignments`), so a Location can be several things at once
-- Nature AND Wildlife AND Adventure -- each with its own per-place relevance.

STRICTLY ADDITIVE. `locations.category` / `locations.subcategory` are NOT
touched, NOT deprecated and keep being written by exactly the same code. They
remain load-bearing: area resolution filters `category = 'Area'` in SQL, the
area reuse radius is keyed off the subcategory literal, the candidate picker
penalises 'Other' and de-duplicates by category, and the mobile map-pin icon
switches on the category string. Nothing in this migration alters any existing
table, so no existing behaviour can change.

The seeded vocabulary below is a FROZEN copy of
app/services/places/category_catalog.py as at this revision. It is inlined
rather than imported because a migration must still run years from now
regardless of how that module has since evolved -- the same reason
f73d25cbe979 inlines its knowledge-type seed rows. Keeping the two in step
afterwards is `category_assignment.sync_category_catalog()`'s job, which is
idempotent and safe to re-run.

Revision ID: 9b3f27c5a814
Revises: 7c1e4a9b3d20
Create Date: 2026-09-14

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9b3f27c5a814"
down_revision: Union[str, None] = "7c1e4a9b3d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


location_categories = sa.table(
    "location_categories",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("kind", sa.String),
    sa.column("slug", sa.String),
    sa.column("display_name", sa.String),
    sa.column("default_priority", sa.Integer),
    sa.column("description", sa.Text),
    sa.column("touristlink_id", sa.Integer),
    sa.column("active", sa.Boolean),
)

# (kind, slug, display_name, default_priority, description, touristlink_id)
SEED_ROWS: list[tuple] = [
    ('theme', 'trail', 'Trail', 85, 'On or serving a walking/trekking route itself.', None),
    ('theme', 'trekking', 'Trekking', 90, 'Directly relevant to a multi-day trek: route, altitude, resupply, permits.', None),
    ('theme', 'nature', 'Nature', 85, 'Natural landscape, terrain or ecosystem.', None),
    ('theme', 'wildlife', 'Wildlife', 80, 'Animals, birds or habitat are a main reason to be here.', None),
    ('theme', 'adventure', 'Adventure', 75, 'Physically demanding or thrill-seeking activity.', None),
    ('theme', 'scenic_spot', 'Scenic Spot', 80, 'Somewhere people go for the view.', None),
    ('theme', 'photography', 'Photography', 60, 'Notably worth photographing.', None),
    ('theme', 'water', 'Water', 65, 'Water is central: river, lake, sea, spring, falls.', None),
    ('theme', 'culture_heritage', 'Culture & Heritage', 80, 'Cultural, artistic or heritage significance.', None),
    ('theme', 'historical', 'Historical', 75, 'Significant for its history or age.', None),
    ('theme', 'religious', 'Religious', 75, 'A place of worship, pilgrimage or religious meaning.', None),
    ('theme', 'local_life', 'Local Life', 70, 'Everyday life of the people who live here.', None),
    ('theme', 'food_drink', 'Food & Drink', 85, 'Somewhere to eat or drink.', None),
    ('theme', 'lodging', 'Lodging', 80, 'Somewhere to sleep.', None),
    ('theme', 'shopping', 'Shopping', 70, 'Somewhere to buy things.', None),
    ('theme', 'nightlife', 'Nightlife', 55, 'Evening and night social venues.', None),
    ('theme', 'transport', 'Transport', 75, 'Getting to, from or through somewhere.', None),
    ('theme', 'practical', 'Practical', 75, "Solves a traveller's practical need: water, power, toilets, permits, supplies.", None),
    ('theme', 'health', 'Health', 85, 'Medical care or health-related facilities.', None),
    ('theme', 'safety', 'Safety', 95, 'Bears on whether someone is safe -- hazards, rescue, police.', None),
    ('theme', 'finance', 'Finance', 70, 'Money: cash, exchange, banking.', None),
    ('theme', 'postal', 'Postal', 45, 'Post and parcels.', None),
    ('theme', 'services', 'Services', 60, 'A service business a traveller might need.', None),
    ('theme', 'entertainment', 'Entertainment', 50, 'Shows, attractions and amusements.', None),
    ('theme', 'sport', 'Sport', 45, 'Sport is played or watched here.', None),
    ('theme', 'education', 'Education', 45, 'Learning, science or study.', None),
    ('theme', 'urban', 'Urban', 45, 'Characteristically part of a built-up townscape.', None),
    ('theme', 'family', 'Family', 50, 'Particularly suited to visiting with children.', None),
    ('theme', 'area', 'Area', 40, 'A named neighbourhood, village, town or district rather than a single venue.', None),
    ('theme', 'other', 'Other', 10, 'Nothing specific established about what this place is.', None),
    ('place_type', 'trail', 'Trail', 90, 'A walking or trekking route.', 34),
    ('place_type', 'trailhead', 'Trailhead', 88, 'Where a trail begins or is entered.', None),
    ('place_type', 'suspension_bridge', 'Suspension Bridge', 85, 'A footbridge carrying a trail over a river or gorge.', None),
    ('place_type', 'bridge', 'Bridge', 70, 'A road or foot bridge.', 140),
    ('place_type', 'mountain_pass', 'Mountain Pass', 92, 'A saddle or col a route crosses.', 234),
    ('place_type', 'base_camp', 'Base Camp', 90, 'A staging camp below a peak.', None),
    ('place_type', 'high_camp', 'High Camp', 88, 'A high-altitude camp above base camp.', None),
    ('place_type', 'acclimatisation_point', 'Acclimatisation Point', 88, 'Where trekkers stop to adjust to altitude.', None),
    ('place_type', 'river_crossing', 'River Crossing', 85, 'A ford or crossing point on a route.', None),
    ('place_type', 'rest_stop', 'Rest Stop', 70, 'A recognised place to pause on a route.', None),
    ('place_type', 'campsite', 'Campsite', 78, 'Somewhere to pitch a tent.', 100),
    ('place_type', 'rv_park', 'RV Park', 55, 'Vehicle camping ground.', 278),
    ('place_type', 'viewpoint', 'Viewpoint', 88, 'A spot specifically for the view.', 215),
    ('place_type', 'scenic_drive', 'Scenic Drive', 70, 'A road travelled for its views.', 209),
    ('place_type', 'landslide_zone', 'Landslide Zone', 95, 'A slope known to slide or shed debris.', None),
    ('place_type', 'avalanche_zone', 'Avalanche Zone', 95, 'Terrain with known avalanche risk.', None),
    ('place_type', 'rockfall_zone', 'Rockfall Zone', 93, 'A section exposed to falling rock.', None),
    ('place_type', 'flood_prone_area', 'Flood-Prone Area', 90, 'Ground that floods or washes out.', None),
    ('place_type', 'crevasse_area', 'Crevasse Area', 93, 'Glaciated ground with crevasse risk.', None),
    ('place_type', 'mountain_peak', 'Mountain Peak', 90, 'A summit.', 32),
    ('place_type', 'mountain_range', 'Mountain Range', 80, 'A connected range of mountains.', 79),
    ('place_type', 'ridge', 'Ridge', 78, 'A ridgeline.', 225),
    ('place_type', 'hill', 'Hill', 65, 'A hill.', 182),
    ('place_type', 'hill_station', 'Hill Station', 70, 'An upland town visited for its climate and views.', 105),
    ('place_type', 'valley', 'Valley', 78, 'A valley.', 183),
    ('place_type', 'glacier', 'Glacier', 85, 'A glacier.', 77),
    ('place_type', 'volcano', 'Volcano', 82, 'A volcano.', 214),
    ('place_type', 'canyon', 'Canyon', 80, 'A canyon or gorge.', 73),
    ('place_type', 'cave', 'Cave', 75, 'A cave.', 33),
    ('place_type', 'desert', 'Desert', 72, 'Desert terrain.', 74),
    ('place_type', 'geologic_feature', 'Geologic Feature', 70, 'A notable rock or landform.', 239),
    ('place_type', 'natural_feature', 'Natural Feature', 68, 'A natural landmark not otherwise typed.', 75),
    ('place_type', 'waterfall', 'Waterfall', 85, 'A waterfall.', 70),
    ('place_type', 'lake', 'Lake', 80, 'A lake.', 31),
    ('place_type', 'river', 'River', 80, 'A river.', 101),
    ('place_type', 'hot_spring', 'Hot Spring', 75, 'A natural hot spring.', 30),
    ('place_type', 'beach', 'Beach', 75, 'A beach.', 29),
    ('place_type', 'island', 'Island', 75, 'An island.', 199),
    ('place_type', 'coastal_area', 'Coastal Area', 70, 'A stretch of coast.', 76),
    ('place_type', 'fjord', 'Fjord', 80, 'A fjord.', 242),
    ('place_type', 'strait', 'Strait', 62, 'A strait.', 241),
    ('place_type', 'backwater', 'Backwater', 65, 'Calm inland waterways.', 181),
    ('place_type', 'wetland', 'Wetland', 72, 'Marsh, bog or wetland.', 227),
    ('place_type', 'dam', 'Dam', 58, 'A dam or reservoir wall.', 102),
    ('place_type', 'canal', 'Canal', 55, 'A canal.', 207),
    ('place_type', 'pier', 'Pier', 58, 'A pier or jetty.', 163),
    ('place_type', 'port_marina', 'Port or Marina', 65, 'A harbour for boats.', 164),
    ('place_type', 'lighthouse', 'Lighthouse', 70, 'A lighthouse.', 165),
    ('place_type', 'national_park', 'National Park', 90, 'A national park.', 71),
    ('place_type', 'state_park', 'State Park', 75, 'A state or provincial park.', 36),
    ('place_type', 'nature_reserve', 'Nature Reserve', 82, 'Protected natural land.', 226),
    ('place_type', 'wildlife_reserve', 'Wildlife Reserve', 85, 'Land protected for its animals.', 103),
    ('place_type', 'bird_sanctuary', 'Bird Sanctuary', 78, 'Protected bird habitat.', 218),
    ('place_type', 'marine_sanctuary', 'Marine Sanctuary', 75, 'Protected marine habitat.', 217),
    ('place_type', 'forest', 'Forest', 80, 'Forest or woodland.', 35),
    ('place_type', 'national_forest', 'National Forest', 78, 'A protected national forest.', 161),
    ('place_type', 'notable_tree', 'Notable Tree', 55, 'A individually notable tree.', 269),
    ('place_type', 'zoo', 'Zoo', 70, 'A zoo or wildlife park.', 169),
    ('place_type', 'aquarium', 'Aquarium', 68, 'An aquarium.', 167),
    ('place_type', 'garden', 'Garden', 68, 'A cultivated garden.', 157),
    ('place_type', 'city_park', 'City Park', 65, 'An urban park.', 40),
    ('place_type', 'picnic_spot', 'Picnic Spot', 60, 'A recognised picnic place.', 232),
    ('place_type', 'recreational_area', 'Recreational Area', 58, 'General recreation ground.', 220),
    ('place_type', 'temple', 'Temple', 85, 'A Hindu or Buddhist temple.', 144),
    ('place_type', 'monastery', 'Monastery', 85, 'A monastery.', 146),
    ('place_type', 'gompa', 'Gompa', 85, 'A Tibetan Buddhist monastery or temple.', None),
    ('place_type', 'stupa', 'Stupa', 83, 'A stupa or chorten.', None),
    ('place_type', 'mani_wall', 'Mani Wall', 70, 'A carved prayer-stone wall beside a trail.', None),
    ('place_type', 'church', 'Church', 80, 'A church.', 145),
    ('place_type', 'mosque', 'Mosque', 80, 'A mosque.', 143),
    ('place_type', 'synagogue', 'Synagogue', 80, 'A synagogue.', 178),
    ('place_type', 'gurdwara', 'Gurdwara', 80, 'A gurdwara.', 176),
    ('place_type', 'shrine', 'Shrine', 75, 'A shrine.', 177),
    ('place_type', 'meditation_centre', 'Meditation Centre', 65, 'A meditation or retreat centre.', 238),
    ('place_type', 'cemetery', 'Cemetery', 60, 'A cemetery or burial ground.', 198),
    ('place_type', 'tomb', 'Tomb', 70, 'A tomb or mausoleum.', 262),
    ('place_type', 'museum', 'Museum', 85, 'A museum.', 25),
    ('place_type', 'gallery', 'Gallery', 72, 'An art gallery.', 204),
    ('place_type', 'historical_site', 'Historical Site', 85, 'A site of historical significance.', 69),
    ('place_type', 'heritage_site', 'Heritage Site', 88, 'A recognised heritage site.', 268),
    ('place_type', 'archaeological_site', 'Archaeological Site', 80, 'An archaeological site.', 264),
    ('place_type', 'ruins', 'Ruins', 78, 'Ruins.', 147),
    ('place_type', 'fort', 'Fort', 80, 'A fort or fortress.', 106),
    ('place_type', 'palace', 'Palace', 82, 'A palace.', 107),
    ('place_type', 'castle', 'Castle', 82, 'A castle.', 202),
    ('place_type', 'monument', 'Monument', 78, 'A monument.', 148),
    ('place_type', 'landmark', 'Landmark', 80, 'A recognised landmark.', 249),
    ('place_type', 'historic_house', 'Historic House', 70, 'A preserved historic house.', 201),
    ('place_type', 'battlefield', 'Battlefield', 70, 'A historic battlefield.', 149),
    ('place_type', 'pyramid', 'Pyramid', 85, 'A pyramid.', 150),
    ('place_type', 'petroglyph', 'Petroglyph Site', 72, 'Rock art or carvings.', 231),
    ('place_type', 'ancient_wall', 'Ancient Wall', 72, 'A surviving ancient wall.', 266),
    ('place_type', 'megalithic_site', 'Megalithic Site', 72, 'Standing stones or megaliths.', 267),
    ('place_type', 'cliff_dwelling', 'Cliff Dwelling', 75, 'Cliff or cave dwellings.', 265),
    ('place_type', 'ghost_town', 'Ghost Town', 68, 'An abandoned settlement.', 233),
    ('place_type', 'gateway', 'Gateway', 65, 'A ceremonial gate or arch.', 263),
    ('place_type', 'clock_tower', 'Clock Tower', 62, 'A clock tower.', 280),
    ('place_type', 'sculpture', 'Sculpture', 58, 'A public sculpture.', 151),
    ('place_type', 'fountain', 'Fountain', 52, 'A public fountain.', 154),
    ('place_type', 'plaza', 'Plaza or Square', 70, 'A public square.', 153),
    ('place_type', 'famous_street', 'Famous Street', 75, 'A street known in its own right.', 216),
    ('place_type', 'roadside_attraction', 'Roadside Attraction', 55, 'A quirky stop by the road.', 637),
    ('place_type', 'teahouse', 'Teahouse', 92, 'A trail teahouse providing both meals and beds to trekkers.', None),
    ('place_type', 'trekking_lodge', 'Trekking Lodge', 90, 'A lodge serving trekkers on a route.', None),
    ('place_type', 'mountain_hut', 'Mountain Hut', 85, 'A basic shelter hut in the mountains.', None),
    ('place_type', 'hotel', 'Hotel', 78, 'A hotel.', 85),
    ('place_type', 'guesthouse', 'Guesthouse', 78, 'A guesthouse.', 273),
    ('place_type', 'lodge', 'Lodge', 75, 'A lodge.', 281),
    ('place_type', 'hostel', 'Hostel', 70, 'A hostel.', 245),
    ('place_type', 'homestay', 'Homestay', 75, 'Staying in a family home.', 272),
    ('place_type', 'resort', 'Resort', 70, 'A resort.', 104),
    ('place_type', 'apartment', 'Apartment', 55, 'A rentable apartment.', 271),
    ('place_type', 'restaurant', 'Restaurant', 80, 'A restaurant.', 12),
    ('place_type', 'cafe', 'Cafe', 75, 'A cafe or coffee house.', 160),
    ('place_type', 'tea_stall', 'Tea Stall', 72, 'A small roadside or trailside tea stall.', None),
    ('place_type', 'bakery', 'Bakery', 70, 'A bakery.', None),
    ('place_type', 'bar', 'Bar', 60, 'A bar.', 155),
    ('place_type', 'pub', 'Pub', 60, 'A pub.', None),
    ('place_type', 'brewery', 'Brewery', 58, 'A brewery.', 253),
    ('place_type', 'winery', 'Winery', 62, 'A winery.', 170),
    ('place_type', 'market', 'Market', 80, 'A market.', 159),
    ('place_type', 'supermarket', 'Supermarket', 68, 'A supermarket or general store.', None),
    ('place_type', 'gear_shop', 'Gear Shop', 85, 'Trekking and outdoor equipment.', None),
    ('place_type', 'handicraft_shop', 'Handicraft Shop', 70, 'Local crafts and handmade goods.', None),
    ('place_type', 'gift_shop', 'Gift Shop', 60, 'A gift or souvenir shop.', None),
    ('place_type', 'shop', 'Shop', 60, 'A general shop.', None),
    ('place_type', 'mall', 'Mall', 62, 'A shopping mall.', 44),
    ('place_type', 'bookstore', 'Bookstore', 55, 'A bookshop.', 158),
    ('place_type', 'specialty_store', 'Specialty Store', 58, 'A specialist retailer.', 257),
    ('place_type', 'hospital', 'Hospital', 95, 'A hospital.', None),
    ('place_type', 'clinic', 'Clinic', 90, 'A clinic.', None),
    ('place_type', 'health_post', 'Health Post', 90, 'A basic rural health post.', None),
    ('place_type', 'altitude_clinic', 'Altitude Clinic', 95, 'A clinic specifically treating altitude sickness.', None),
    ('place_type', 'pharmacy', 'Pharmacy', 85, 'A pharmacy.', None),
    ('place_type', 'police_post', 'Police Post', 90, 'A police station or post.', None),
    ('place_type', 'rescue_post', 'Rescue Post', 93, 'A mountain rescue base.', None),
    ('place_type', 'helipad', 'Helipad', 88, 'A helicopter landing point.', None),
    ('place_type', 'permit_checkpost', 'Permit Checkpost', 90, 'Where trekking permits or park entry are checked.', None),
    ('place_type', 'atm', 'ATM', 88, 'A cash machine.', None),
    ('place_type', 'bank', 'Bank', 80, 'A bank branch.', None),
    ('place_type', 'money_exchange', 'Money Exchange', 82, 'A currency exchange.', None),
    ('place_type', 'post_office', 'Post Office', 60, 'A post office.', None),
    ('place_type', 'drinking_water', 'Drinking Water', 90, 'A safe drinking-water point.', None),
    ('place_type', 'charging_point', 'Charging Point', 85, 'Somewhere to charge devices.', None),
    ('place_type', 'wifi_spot', 'WiFi Spot', 80, 'Somewhere with internet access.', None),
    ('place_type', 'public_toilet', 'Public Toilet', 80, 'A public toilet.', None),
    ('place_type', 'laundry', 'Laundry', 65, 'A laundry service.', None),
    ('place_type', 'internet_cafe', 'Internet Cafe', 65, 'An internet cafe.', 14),
    ('place_type', 'tourist_office', 'Tourist Office', 75, 'An official tourist information office.', 15),
    ('place_type', 'visitor_centre', 'Visitor Centre', 72, 'A park or site visitor centre.', 210),
    ('place_type', 'tour_operator', 'Tour Operator', 72, 'A trekking or tour agency.', 108),
    ('place_type', 'travel_agency', 'Travel Agency', 65, 'A travel agency.', 109),
    ('place_type', 'porter_service', 'Porter Service', 85, 'Porters and guides for hire.', None),
    ('place_type', 'embassy', 'Embassy', 70, 'An embassy or consulate.', 16),
    ('place_type', 'community_centre', 'Community Centre', 55, 'A community hall or centre.', 175),
    ('place_type', 'farm', 'Farm', 60, 'A working farm.', 235),
    ('place_type', 'airport', 'Airport', 90, 'An airport or airstrip.', 80),
    ('place_type', 'airline_office', 'Airline Office', 65, 'An airline ticket office.', None),
    ('place_type', 'ticketing_office', 'Ticketing Office', 65, 'A travel ticketing office.', None),
    ('place_type', 'bus_station', 'Bus Station', 80, 'A bus station or stand.', 81),
    ('place_type', 'railway_station', 'Railway Station', 80, 'A railway station.', 82),
    ('place_type', 'metro_station', 'Metro Station', 72, 'A metro or subway station.', 240),
    ('place_type', 'taxi_jeep_stand', 'Taxi or Jeep Stand', 75, 'Where shared jeeps and taxis wait.', None),
    ('place_type', 'ferry_terminal', 'Ferry Terminal', 70, 'A ferry terminal.', 83),
    ('place_type', 'cable_car', 'Cable Car', 72, 'A cable car or ropeway.', 236),
    ('place_type', 'heritage_railway', 'Heritage Railway', 68, 'A preserved historic railway.', 248),
    ('place_type', 'road_highway', 'Road or Highway', 55, 'A named road or highway.', 259),
    ('place_type', 'tunnel', 'Tunnel', 52, 'A tunnel.', 237),
    ('place_type', 'ski_resort', 'Ski Resort', 72, 'A ski resort.', 99),
    ('place_type', 'diving_spot', 'Diving Spot', 72, 'A dive site.', 72),
    ('place_type', 'golf_course', 'Golf Course', 55, 'A golf course.', 98),
    ('place_type', 'stadium', 'Stadium', 62, 'A stadium.', 200),
    ('place_type', 'sporting_area', 'Sporting Area', 55, 'A sports ground.', 41),
    ('place_type', 'pool', 'Swimming Pool', 52, 'A swimming pool.', 42),
    ('place_type', 'fitness_centre', 'Fitness Centre', 48, 'A gym.', 43),
    ('place_type', 'amusement_park', 'Amusement Park', 70, 'An amusement park.', 168),
    ('place_type', 'water_park', 'Water Park', 65, 'A water park.', None),
    ('place_type', 'theatre', 'Theatre', 68, 'A theatre.', 179),
    ('place_type', 'concert_hall', 'Concert Hall', 68, 'A concert hall.', 39),
    ('place_type', 'opera_house', 'Opera House', 72, 'An opera house.', 139),
    ('place_type', 'cinema', 'Cinema', 55, 'A cinema.', 156),
    ('place_type', 'nightclub', 'Nightclub', 58, 'A nightclub.', 38),
    ('place_type', 'casino', 'Casino', 55, 'A casino.', 86),
    ('place_type', 'fairground', 'Fairground', 58, 'A fairground.', 250),
    ('place_type', 'observatory', 'Observatory', 70, 'An astronomical observatory.', 211),
    ('place_type', 'planetarium', 'Planetarium', 62, 'A planetarium.', 243),
    ('place_type', 'library', 'Library', 58, 'A library.', 212),
    ('place_type', 'university', 'University', 60, 'A university or college.', 228),
    ('place_type', 'school', 'School', 48, 'A school.', 261),
    ('place_type', 'research_centre', 'Research Centre', 55, 'A research institute.', 213),
    ('place_type', 'skyscraper', 'Skyscraper', 65, 'A skyscraper.', 138),
    ('place_type', 'key_building', 'Key Building', 60, 'An architecturally notable building.', 26),
    ('place_type', 'government_building', 'Government Building', 50, 'A government building.', 171),
    ('place_type', 'town_hall', 'Town Hall', 52, 'A town hall.', 251),
    ('place_type', 'courthouse', 'Courthouse', 45, 'A courthouse.', 172),
    ('place_type', 'parliament', 'Parliament', 58, 'A parliament building.', 173),
    ('place_type', 'convention_centre', 'Convention Centre', 45, 'A convention centre.', 152),
    ('place_type', 'mine', 'Mine', 50, 'A mine.', 208),
    ('place_type', 'power_station', 'Power Station', 40, 'A power station.', 229),
    ('place_type', 'area', 'Area', 40, 'A named neighbourhood, village, town or district rather than a single venue.', None),
    ('place_type', 'other', 'Other', 10, 'Nothing specific established about what this place is.', None),
]


def upgrade() -> None:
    op.create_table(
        "location_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("default_priority", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("touristlink_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "slug", name="uq_location_categories_kind_slug"),
        sa.CheckConstraint(
            "default_priority >= 0 AND default_priority <= 100",
            name="ck_location_categories_default_priority_range",
        ),
    )
    op.create_index("ix_location_categories_kind", "location_categories", ["kind"])

    op.create_table(
        "location_category_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["location_categories.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "location_id", "category_id", name="uq_location_category_assignment"
        ),
        sa.CheckConstraint(
            "relevance >= 0 AND relevance <= 100",
            name="ck_location_category_assignments_relevance_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_location_category_assignments_confidence_range",
        ),
    )
    op.create_index(
        "ix_location_category_assignments_location_relevance",
        "location_category_assignments",
        ["location_id", "relevance"],
    )
    op.create_index(
        "ix_location_category_assignments_category",
        "location_category_assignments",
        ["category_id", "relevance"],
    )
    # At most one primary theme and one primary place_type per Location,
    # enforced by the database rather than merely intended by the service.
    op.create_index(
        "uq_location_category_primary_per_kind",
        "location_category_assignments",
        ["location_id", "kind"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.bulk_insert(
        location_categories,
        [
            {
                "id": uuid.uuid4(),
                "kind": kind,
                "slug": slug,
                "display_name": display_name,
                "default_priority": default_priority,
                "description": description,
                "touristlink_id": touristlink_id,
                "active": True,
            }
            for (
                kind,
                slug,
                display_name,
                default_priority,
                description,
                touristlink_id,
            ) in SEED_ROWS
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "uq_location_category_primary_per_kind",
        table_name="location_category_assignments",
    )
    op.drop_index(
        "ix_location_category_assignments_category",
        table_name="location_category_assignments",
    )
    op.drop_index(
        "ix_location_category_assignments_location_relevance",
        table_name="location_category_assignments",
    )
    op.drop_table("location_category_assignments")
    op.drop_index("ix_location_categories_kind", table_name="location_categories")
    op.drop_table("location_categories")
