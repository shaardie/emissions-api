# Copyright 2019, The Emissions API Developers
# https://emissions-api.org
# This software is available under the terms of an MIT license.
# See LICENSE fore more information.
"""Web application to deliver the data stored in the database via an API to
the users.
"""
from functools import wraps
import logging
import dateutil.parser

import connexion
import geojson
from flask import redirect

import emissionsapi.db
from emissionsapi.country_bounding_boxes import country_bounding_boxes
from emissionsapi.utils import bounding_box_to_wkt, polygon_to_wkt, \
    RESTParamError

# Logger
logger = logging.getLogger(__name__)


def parse_date(*keys):
    """Function wrapper replacing string date arguments with
    datetime.datetime

    :param keys: keys to be parsed and replaced
    :type keys: list
    :return: wrapper function
    :rtype: func
    """
    def wrap(f):
        def wrapped_f(*args, **kwargs):
            for key in keys:
                logger.debug(f'Try to parse {key} as date')
                date = kwargs.get(key)
                if date is None:
                    continue
                try:
                    kwargs[key] = dateutil.parser.parse(date)
                except ValueError:
                    return f'Invalid {key}', 400
            return f(*args, **kwargs)
        return wrapped_f
    return wrap


def parse_wkt_polygon(f):
    """Function wrapper replacing 'geoframe', 'country' and 'polygon' with a
    WKT polygon.

    :param f: Function to call
    :type f: Function
    :raises e: Possible exception of f
    :return: Result of f
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        geoframe = kwargs.pop('geoframe', None)
        country = kwargs.pop('country', None)
        polygon = kwargs.pop('polygon', None)
        # Parse parameter geoframe
        if geoframe is not None:
            try:
                logger.debug('Try to parse geoframe')
                kwargs['wkt_polygon'] = bounding_box_to_wkt(*geoframe)
            except ValueError:
                return 'Invalid geoparam', 400
        # parse parameter country
        elif country is not None:
            logger.debug('Try to parse country')
            if country not in country_bounding_boxes:
                return 'Unknown country code.', 400
            kwargs['wkt_polygon'] = bounding_box_to_wkt(
                *country_bounding_boxes[country][1])
        # parse parameter polygon
        elif polygon is not None:
            try:
                logger.debug('Try to parse polygon')
                kwargs['wkt_polygon'] = polygon_to_wkt(polygon)
            except RESTParamError as err:
                return str(err), 400
        return f(*args, **kwargs)
    return decorated


@parse_wkt_polygon
@parse_date('begin', 'end')
@emissionsapi.db.with_session
def get_data(session, wkt_polygon=None, begin=None, end=None, limit=None,
             offset=None):
    """Get data in GeoJSON format.

    :param session: SQLAlchemy session
    :type session: sqlalchemy.orm.session.Session
    :param wkt_polygon: WKT defining the polygon
    :type wkt_polygon: string
    :param begin: Filter out points before this date
    :type begin: datetime.datetime
    :param end: filter out points after this date
    :type end: datetime.datetime
    :param limit: Limit number of returned items
    :type limit: int
    :param offset: Specify the offset of the first item to return
    :type offset: int
    :return: Feature Collection with requested Points
    :rtype: geojson.FeatureCollection
    """
    # Init feature list
    features = []
    # Iterate through database query
    query = emissionsapi.db.get_points(
        session, polygon=wkt_polygon, begin=begin, end=end)
    # Apply limit and offset
    query = emissionsapi.db.limit_offset_query(
        query, limit=limit, offset=offset)

    for obj, longitude, latitude in query:
        # Create and append single features.
        features.append(geojson.Feature(
            geometry=geojson.Point((longitude, latitude)),
            properties={
                "carbonmonoxide": obj.value,
                "timestamp": obj.timestamp
            }))
    # Create feature collection from gathered points
    feature_collection = geojson.FeatureCollection(features)
    return feature_collection


@parse_wkt_polygon
@parse_date('begin', 'end')
@emissionsapi.db.with_session
def get_average(session, wkt_polygon=None, begin=None, end=None,
                limit=None, offset=None):
    """Get daily average for a specified area filtered by time.

    :param session: SQLAlchemy session
    :type session: sqlalchemy.orm.session.Session
    :param wkt_polygon: WKT defining the polygon
    :type wkt_polygon: string
    :param begin: Filter out points before this date
    :type begin: datetime.datetime
    :param end: filter out points after this date
    :type end: datetime.datetime
    :param limit: Limit number of returned items
    :type limit: int
    :param offset: Specify the offset of the first item to return
    :type offset: int
    :return: List of calculated averages
    :rtype: list
    """
    # Get averages
    query = emissionsapi.db.get_averages(
        session, polygon=wkt_polygon, begin=begin, end=end)
    # Apply limit and offset
    query = emissionsapi.db.limit_offset_query(
        query, limit=limit, offset=offset)

    result = []
    for avg, max_time, min_time, _ in query:
        result.append({
            'average': avg,
            'start': min_time,
            'end': max_time})
    return result


# Create connexion app
app = connexion.App(__name__)

# Add swagger description to api
app.add_api('openapi.yml', )

# Create app to run with wsgi server
application = app.app


@app.route('/')
def home():
    """Redirect / to the swagger ui

    :return: Redirect response
    :rtype: werkzeug.wrappers.response.Response
    """
    return redirect('/ui', code=302)


def entrypoint():
    """Entrypoint for running this as a module or from the binary.
    It starts the Connexion Debug Server. It is not meant to be used for
    production, but only during the development.
    """
    logger.info("Starting the Connexion Debug Server")
    app.run(host='127.0.0.1')


if __name__ == "__main__":
    entrypoint()
