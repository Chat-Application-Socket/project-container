from chat import create_app


def test_app_creation():
    """Verify application factory initializes correctly."""
    app = create_app()
    assert app is not None
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
