"""
Configuration module for the Flight Fare Monitoring & Comparison Agent.
Provides default settings, airport metadata, approved domain allowlists, and configuration schemas.
"""
import os
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta

# List of 15 South Indian departure airports with metadata
SOUTH_INDIA_AIRPORTS: Dict[str, Dict[str, str]] = {
    "MAA": {"name": "Chennai International Airport", "city": "Chennai", "state": "Tamil Nadu"},
    "BLR": {"name": "Kempegowda International Airport", "city": "Bengaluru", "state": "Karnataka"},
    "HYD": {"name": "Rajiv Gandhi International Airport", "city": "Hyderabad", "state": "Telangana"},
    "COK": {"name": "Cochin International Airport", "city": "Kochi", "state": "Kerala"},
    "TRV": {"name": "Thiruvananthapuram International Airport", "city": "Thiruvananthapuram", "state": "Kerala"},
    "CCJ": {"name": "Calicut International Airport", "city": "Kozhikode", "state": "Kerala"},
    "CNN": {"name": "Kannur International Airport", "city": "Kannur", "state": "Kerala"},
    "IXE": {"name": "Mangaluru International Airport", "city": "Mangaluru", "state": "Karnataka"},
    "CJB": {"name": "Coimbatore International Airport", "city": "Coimbatore", "state": "Tamil Nadu"},
    "IXM": {"name": "Madurai Airport", "city": "Madurai", "state": "Tamil Nadu"},
    "TRZ": {"name": "Tiruchirappalli International Airport", "city": "Tiruchirappalli", "state": "Tamil Nadu"},
    "VGA": {"name": "Vijayawada International Airport", "city": "Vijayawada", "state": "Andhra Pradesh"},
    "VTZ": {"name": "Visakhapatnam International Airport", "city": "Visakhapatnam", "state": "Andhra Pradesh"},
    "RJA": {"name": "Rajahmundry Airport", "city": "Rajahmundry", "state": "Andhra Pradesh"},
    "TIR": {"name": "Tirupati Airport", "city": "Tirupati", "state": "Andhra Pradesh"},
}

# Dubai-area arrival airports (DXB and SHJ)
DESTINATION_AIRPORTS: Dict[str, Dict[str, str]] = {
    "DXB": {"name": "Dubai International Airport", "city": "Dubai", "country": "UAE"},
    "SHJ": {"name": "Sharjah International Airport", "city": "Sharjah", "country": "UAE"},
}

# Ground transport estimates to Dubai Downtown/Central (INR)
DEFAULT_GROUND_TRANSPORT_INR: Dict[str, float] = {
    "DXB": 0.0,      # Direct arrival in Dubai
    "SHJ": 500.0,    # Intercity bus / shared taxi Sharjah to Dubai
}

# Domestic Indian Carriers (to be filtered/de-prioritized when focusing on International Airlines)
INDIAN_AIRLINES: set = {
    "indigo",
    "air india express",
    "air india",
    "spicejet",
    "akasa air",
    "akasa",
    "vistara"
}

# Major International Airlines operating South India to UAE corridor
INTERNATIONAL_AIRLINES: set = {
    "emirates",
    "flydubai",
    "air arabia",
    "etihad",
    "etihad airways",
    "oman air",
    "qatar airways",
    "gulf air",
    "kuwait airways",
    "saudia",
    "srilankan",
    "srilankan airlines"
}


def is_international_airline(airline_name: str) -> bool:
    """Returns True if the airline is an international carrier (not an Indian domestic carrier)."""
    if not airline_name:
        return False
    name_clean = airline_name.strip().lower()
    for indian in INDIAN_AIRLINES:
        if indian in name_clean:
            return False
    return True

# Strict Allowlist of Approved Flight Data Sources
# Categorized with reliability ratings:
# 100: Official Airline
# 80: Verified Flight Search (Metasearch)
# 60: Major Travel OTA
APPROVED_SOURCES: Dict[str, Dict] = {
    # Official Airlines
    "goindigo.in": {"name": "IndiGo", "type": "Official Airline", "reliability": 100},
    "airindiaexpress.com": {"name": "Air India Express", "type": "Official Airline", "reliability": 100},
    "airarabia.com": {"name": "Air Arabia", "type": "Official Airline", "reliability": 100},
    "flydubai.com": {"name": "flydubai", "type": "Official Airline", "reliability": 100},
    "emirates.com": {"name": "Emirates", "type": "Official Airline", "reliability": 100},
    "etihad.com": {"name": "Etihad Airways", "type": "Official Airline", "reliability": 100},
    "airindia.com": {"name": "Air India", "type": "Official Airline", "reliability": 100},
    "spicejet.com": {"name": "SpiceJet", "type": "Official Airline", "reliability": 100},
    "qatarairways.com": {"name": "Qatar Airways", "type": "Official Airline", "reliability": 100},
    "omanair.com": {"name": "Oman Air", "type": "Official Airline", "reliability": 100},
    "gulfair.com": {"name": "Gulf Air", "type": "Official Airline", "reliability": 100},
    "kuwaitairways.com": {"name": "Kuwait Airways", "type": "Official Airline", "reliability": 100},
    "saudia.com": {"name": "Saudia", "type": "Official Airline", "reliability": 100},

    # Flight Search / Metasearch
    "google.com": {"name": "Google Flights", "type": "Verified Flight Search", "reliability": 80},
    "skyscanner.net": {"name": "Skyscanner", "type": "Verified Flight Search", "reliability": 80},
    "kayak.com": {"name": "Kayak", "type": "Verified Flight Search", "reliability": 80},
    "wego.co.in": {"name": "Wego", "type": "Verified Flight Search", "reliability": 80},
    "wego.com": {"name": "Wego Global", "type": "Verified Flight Search", "reliability": 80},
    "momondo.com": {"name": "Momondo", "type": "Verified Flight Search", "reliability": 80},

    # Major Travel OTA
    "makemytrip.com": {"name": "MakeMyTrip", "type": "Travel OTA", "reliability": 60},
    "cleartrip.com": {"name": "Cleartrip", "type": "Travel OTA", "reliability": 60},
    "ixigo.com": {"name": "ixigo", "type": "Travel OTA", "reliability": 60},
    "expedia.co.in": {"name": "Expedia", "type": "Travel OTA", "reliability": 60},
    "expedia.com": {"name": "Expedia Global", "type": "Travel OTA", "reliability": 60},
    "trip.com": {"name": "Trip.com", "type": "Travel OTA", "reliability": 60},
}

# Forbidden domain patterns (social media, forums, blogs, search snippets)
STRICTLY_DISALLOWED_PATTERNS: List[str] = [
    "reddit.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "quora.com", "medium.com", "blogspot.com",
    "wordpress.com", "tripadvisor.com/forum", "flyertalk.com"
]


class MonitorConfig(BaseModel):
    """User Configuration with full customization and persistence."""
    departure_region: str = "South India"
    destination: str = "Dubai (DXB, SHJ)"
    cabin: str = "Economy"
    travel_date: str = Field(default_factory=lambda: (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"))
    passengers: int = 1
    baggage: str = "20kg Checked Bag"  # Options: 'Cabin Only (7kg)', '15kg Checked Bag', '20kg Checked Bag', '30kg Checked Bag'
    maximum_stops: int = 2
    maximum_journey_duration_hours: int = 24
    refresh_interval_seconds: int = 300  # 5 minutes
    number_of_results: int = 5
    consecutive_days: int = 7  # Monitor 7 consecutive dates (full 7-day week) for price comparison
    departure_airports: List[str] = list(SOUTH_INDIA_AIRPORTS.keys())
    destination_airports: List[str] = list(DESTINATION_AIRPORTS.keys())
    ground_transport_costs: Dict[str, float] = Field(default_factory=lambda: DEFAULT_GROUND_TRANSPORT_INR.copy())
    prefer_international_airlines: bool = True  # Focus primarily on International Airlines (Emirates, Air Arabia, flydubai, etc.)
    alert_price_drop_absolute: float = 300.0  # ₹300
    alert_price_drop_percentage: float = 5.0   # 5%
    auto_refresh_enabled: bool = True
    enable_live_google_flights: bool = True
    groq_api_key: str = Field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    amadeus_api_key: str = ""
    amadeus_api_secret: str = ""
    rapidapi_key: str = ""

    def get_consecutive_dates(self) -> List[str]:
        """Returns the list of consecutive dates (default 7) starting from travel_date."""
        try:
            base = datetime.strptime(self.travel_date, "%Y-%m-%d")
        except Exception:
            base = datetime.now() + timedelta(days=14)
        return [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(self.consecutive_days)]

