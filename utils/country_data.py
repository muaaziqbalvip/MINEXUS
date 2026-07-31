"""
MI NEXUS - Country Selection & Regional Pricing

Provides a country list for the account-creation flow, a rough
Quotex-availability flag per country (for user guidance only - not a
guarantee, since broker availability can change and is enforced by
Quotex's own geolocation/compliance systems, not by us), and the
regional pricing split: Pakistan gets the Rs-denominated paid plans,
every other country sees the Quotex-deposit-tier path as their primary
option.

IMPORTANT HONESTY NOTE: this list is a best-effort guide based on
generally reported broker availability, not an official or guaranteed
source. Quotex's own registration flow is the final authority on whether
a given user can actually sign up from their location - always defer to
that if there's a conflict.
"""

# (display name, ISO-ish code) - broad, common-sense list covering most
# of the world. Kept alphabetical for easy scanning in the picker UI.
COUNTRIES = [
    ("Afghanistan", "AF"), ("Algeria", "DZ"), ("Argentina", "AR"),
    ("Bangladesh", "BD"), ("Brazil", "BR"), ("Cambodia", "KH"),
    ("Cameroon", "CM"), ("Chile", "CL"), ("Colombia", "CO"),
    ("Egypt", "EG"), ("Ethiopia", "ET"), ("Ghana", "GH"),
    ("India", "IN"), ("Indonesia", "ID"), ("Iraq", "IQ"),
    ("Jordan", "JO"), ("Kenya", "KE"), ("Kuwait", "KW"),
    ("Malaysia", "MY"), ("Mexico", "MX"), ("Morocco", "MA"),
    ("Nepal", "NP"), ("Nigeria", "NG"), ("Oman", "OM"),
    ("Pakistan", "PK"), ("Peru", "PE"), ("Philippines", "PH"),
    ("Qatar", "QA"), ("Saudi Arabia", "SA"), ("South Africa", "ZA"),
    ("Sri Lanka", "LK"), ("Tanzania", "TZ"), ("Thailand", "TH"),
    ("Turkey", "TR"), ("UAE", "AE"), ("Uganda", "UG"),
    ("Uzbekistan", "UZ"), ("Vietnam", "VN"), ("Zambia", "ZM"),
    ("Other / Not Listed", "XX"),
]

# Countries Quotex is broadly reported as NOT operating in. Kept
# deliberately short since sources vary and Quotex's own signup flow is
# the real authority - this is just a heads-up, never a hard block.
GENERALLY_RESTRICTED = {"US", "CA", "GB", "RU", "HK", "ID"}
# EU/EEA member states, also generally excluded per broker restrictions
GENERALLY_RESTRICTED |= {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
    "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
    "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO",
}


def country_label(code):
    for name, c in COUNTRIES:
        if c == code:
            return name
    return code


def is_generally_restricted(code):
    return code in GENERALLY_RESTRICTED


def get_pricing_region(country_code):
    """
    Returns 'pk' for Pakistan (Rs-denominated manual plans shown as the
    primary option) or 'intl' for everyone else (Quotex deposit tiers
    shown as the primary option, since local payment rails for Rs QR
    codes don't apply outside Pakistan).
    """
    return "pk" if country_code == "PK" else "intl"
