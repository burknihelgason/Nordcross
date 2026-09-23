from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)
    from . import views

    app.register_blueprint(views.bp)
    return app
