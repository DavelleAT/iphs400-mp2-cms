"""T00: the walking skeleton. These pass in the fresh template.

Do not delete them. If a change breaks them, the change broke the app's front
door.
"""


def test_admin_console_answers(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "hello admin" in response.text.lower()


def test_public_home_answers(client):
    response = client.get("/")
    assert response.status_code == 200


def test_publish_writes_a_site(tmp_path):
    from app.publish import render_site

    out = render_site(tmp_path / "site")
    assert (out / "index.html").exists() and (out / "style.css").exists()


def test_published_html_uses_relative_paths(tmp_path):
    """Root-absolute paths break on GitHub Pages project URLs (rubric F2)."""
    from app.publish import render_site

    html = (render_site(tmp_path / "site") / "index.html").read_text()
    assert 'href="/' not in html and 'src="/' not in html
