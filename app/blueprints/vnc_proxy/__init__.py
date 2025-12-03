from flask import Blueprint

bp = Blueprint('vnc_proxy', __name__)

from . import routes
