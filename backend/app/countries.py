import pycountry


COUNTRIES = tuple(
    {"code": country.alpha_2, "name": country.name}
    for country in sorted(pycountry.countries, key=lambda item: item.alpha_2)
)
COUNTRY_CODES = frozenset(country["code"] for country in COUNTRIES)
