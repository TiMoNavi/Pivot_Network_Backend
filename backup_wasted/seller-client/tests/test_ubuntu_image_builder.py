from seller_client_app.ubuntu_image_builder import extract_base_image, validate_dockerfile_base_image


def test_extract_base_image() -> None:
    dockerfile = """
    # comment
    FROM pivotcompute/runtime-base:ubuntu-22.04
    RUN echo ok
    """
    assert extract_base_image(dockerfile) == "pivotcompute/runtime-base:ubuntu-22.04"


def test_validate_base_image_rejects_non_managed() -> None:
    dockerfile = "FROM python:3.11-slim\nRUN echo bad\n"
    try:
        validate_dockerfile_base_image(dockerfile, "pivotcompute/runtime-base:ubuntu-22.04")
    except Exception as exc:  # noqa: BLE001
        assert "must be `pivotcompute/runtime-base:ubuntu-22.04`" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected validation failure")
