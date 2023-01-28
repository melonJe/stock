from flask import Blueprint, Response
import json

sun = Blueprint('sun', __name__)
sun.url_prefix = '/sun'

APPLICATION_JSON = 'application/json'


@sun.route('/')
def index():
    return Response(json.dumps("Sun API"), mimetype=APPLICATION_JSON)


@sun.route('/equinox')
def phase_today():
    return Response(json.dumps({"equinox": 1}), mimetype=APPLICATION_JSON)
