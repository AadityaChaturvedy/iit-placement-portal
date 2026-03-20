from flask import Flask, request, flash, render_template
from models import db
from config import Config

app = Flask(__name__)
app.secret_key = 'testkey'
app.config.from_object(Config)

db.init_app(app)

def index():
    return "Database setup done."

if __name__ == '__main__':
    app.run(debug=True)