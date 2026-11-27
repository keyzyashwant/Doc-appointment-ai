"""The database-backed specialty catalog used in voice guidance."""

_SPECIALITY_CATALOG: tuple[str, ...] = ()


def set_speciality_catalog(specialities: list[str]) -> None:
    global _SPECIALITY_CATALOG
    _SPECIALITY_CATALOG = tuple(specialities)


def get_speciality_catalog() -> tuple[str, ...]:
    return _SPECIALITY_CATALOG