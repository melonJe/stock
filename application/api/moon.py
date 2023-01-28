import datetime
from flask import Blueprint, Response
import json


moon = Blueprint('moon', __name__)
moon.url_prefix = '/moon'

APPLICATION_JSON = 'application/json'


@moon.route('/')
def index():
    return Response(json.dumps("Moon API"), mimetype=APPLICATION_JSON)


def _validate_inputs(year, month, day):
    try:
        datetime.datetime(int(year), int(month), int(day))
    except ValueError:
        return False

    return True


@moon.route('/phase')
def phase_today():
    return Response(json.dumps({"phase": 2}), mimetype=APPLICATION_JSON)


@moon.route('/phase/<year>/<month>/<day>')
def phase_specific_day(year, month, day):

    return Response(json.dumps({"phase_specific_day": 3}), mimetype=APPLICATION_JSON)

# https://www.moongiant.com/calendar/september/2021
