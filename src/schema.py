"""Record types and shared validation for interchangeable stores."""

SCHEMAS = {
    "person": dict(identifier=int, time=int, locale=str, user_agent=str),
    "query": dict(identifier=int, time=int, content=str, person=int),
    "result": dict(
        identifier=int,
        time=int,
        output=str,
        state=str,
        failure=str,
        query=int,
        duration=int,
    ),
}
WINDOW_SECONDS = 9 * 60


def validate(entity, values, partial=False):
    """Validate field names and exact Python types."""
    schema = SCHEMAS[entity]
    if not values or not set(values) <= set(schema):
        raise ValueError("Unknown fields or empty record")
    if not partial and set(values) != set(schema):
        raise ValueError("Required fields are missing")
    for name, value in values.items():
        if type(value) is not schema[name]:
            raise ValueError(f"Invalid type: {name}")
