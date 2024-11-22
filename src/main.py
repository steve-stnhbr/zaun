import os
import redis
import asyncio
from quart import Quart, request, jsonify, current_app
from api.tado import TadoTemperatureAPI
from dotenv import load_dotenv
import requests
from datetime import datetime

MAX_AGE_STATUS = 60 * 60 * 24 * 5 # 5 days

DOTENV_PATH = os.getenv('DOTENV_PATH')
if DOTENV_PATH is not None:
    print("Loading dotenv from " + DOTENV_PATH)
    load_dotenv(dotenv_path=DOTENV_PATH)

from marshmallow import Schema, fields, ValidationError, validate

class PutStatusRequestSchema(Schema):
    status = fields.String(required=True, validate=validate.OneOf(["home", "away"]))
    timestamp = fields.Float(required=True)
    preferred_temperature = fields.Float(required=True)


class GetStatusResponseSchema(Schema):
    status = fields.String()
    timestamp = fields.Float()
    preferred_temperature = fields.Float()

class PutStatusResponseSchema(Schema):
    success = fields.Boolean()
    message = fields.String()
    data = fields.Nested(PutStatusRequestSchema)

DEBUG = os.getenv('DEBUG', False)
PORT = os.getenv('PORT', 8080)

SERVER_PASSWORD = os.getenv('SERVER_PASSWORD')

REDIS_PORT = os.getenv('REDIS_PORT', 6379)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

MIN_TEMPERATURE = os.getenv('MIN_TEMPERATURE', 16)

TADO_EMAIL = os.getenv('TADO_EMAIL')
TADO_PASSWORD = os.getenv('TADO_PASSWORD')
TADO_CLIENT_SECRET = os.getenv('TADO_CLIENT_SECRET')

print(f"Starting server with\n\tREDIS_PORT: {REDIS_PORT}\n\tREDIS_HOST:{REDIS_HOST}\n\tTADO_EMAIL:{TADO_EMAIL}\n\tTADO_CLIENT_SECRET:{TADO_CLIENT_SECRET}")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
try:
    temperature_client = TadoTemperatureAPI(email=TADO_EMAIL, password=TADO_PASSWORD, client_secret=TADO_CLIENT_SECRET)
except requests.exceptions.HTTPError as http_err:
    response = http_err.response
    request = response.request
    print("Request URL:", request.url, "Body:", request.body)
    print("Response:", response.json())
    exit(2)

try:
    redis_client.ping()
except redis.exceptions.ConnectionError as err:
    print("Error connecting to Redis:", err)
    exit(2)

app = Quart(__name__)

@app.before_request
async def authenticate():
    # check if the authentication header is present and valid
    if request.headers.get('Authorization') != f"Bearer {SERVER_PASSWORD}":
        return jsonify({'success': False,'message': 'Authentication failed'}), 401

@app.before_request
async def prefix_identifier():
    # Create a copy of the view args to modify
    if request.view_args and 'identifier' in request.view_args:
        request.view_args['identifier'] = f"person:{request.view_args['identifier'].lower()}"

@app.before_serving
async def startup():
    app.add_background_task(houskeeping_loop)

@app.route('/', methods=['GET'])
def get_health():
    return jsonify({'success': True, 'message': "Server is healthy"}), 200

@app.route('/status/<identifier>', methods=['GET'])
def get_status(identifier):
    redis_data = redis_client.hgetall(identifier)
    if redis_data:
        return jsonify({'success':True, 'data':redis_data}), 200
    else:
        return jsonify({'success':False, 'message':"Status not found", 'data':None}), 404

@app.route('/status/<identifier>', methods=['PUT'])
async def put_status(identifier):
    body = await request.json
    print(body)
    # Validate request
    schema = PutStatusRequestSchema()
    
    try:
        # Validate request body against schema data types
        result = schema.load(body)
    except ValidationError as err:
        return jsonify(err.messages), 400
    
    body['user_timestamp'] = body['timestamp']
    body['timestamp'] = datetime.now().timestamp()
    data = {'status': body['status'], 'preferred_temperature': body['preferred_temperature'], 'timestamp': body['timestamp']}
    redis_client.hset(identifier, mapping=data)

    if body['status'] == "home":
        redis_client.sadd("temps_at_home", identifier)
    else:
        redis_client.srem("temps_at_home", identifier)

    set_temperature = await update_temperature()
    data['temperature'] = set_temperature
    
    return jsonify({'success':True, 'message':"Status updated successfully", 'data':data}), 200


@app.route('/temperature', methods=['GET'])
def get_temperature():
    return jsonify({'success':True, 'message':"Temperature retrieved successfully", 'data':{'temperature': temperature_client.get_temperature()}}), 200

@app.route('/status', methods=['GET'])
def get_statuses():
    # check if home query is set
    home_query = request.args.get('home', None)
    away_query = request.args.get('away', None)
    if home_query is None and away_query is None:
        return jsonify({'success': False, 'message': "No query provided! Provide either 'home' or 'away'"}), 400
    if home_query is not None and away_query is not None:
        return jsonify({'success': False, 'message': "Too many queries provided! Only provide either 'home' or 'away'"}), 400
    if home_query is not None:
        names = redis_client.smembers('temps_at_home')
    if away_query is not None:
        print(redis_client.keys('person:*'))
        names = set(redis_client.keys('person:*')) - set(redis_client.smembers('temps_at_home'))
    
    return jsonify({'success': True, 'data': { 'names': list(names) }}), 200

async def update_temperature() -> int:
    print("Updating temperature...")
    temperature = calculate_temperature()
    print("Setting temperature to: %s" % temperature)
    try:
        temperature_client.set_temperature(temperature)
    except requests.exceptions.HTTPError as http_err:
        response = http_err.response
        request = response.request
        print("Request URL:", request.url, "Body:", request.body)
        print("Response:", response.json())
        exit(2)
    return temperature

def calculate_temperature():
    # get all names from temps_at_home set
    names = redis_client.smembers('temps_at_home')

    # calculate average temperature
    max_temperature = MIN_TEMPERATURE
    for name in names:
        max_temperature = max(max_temperature, float(redis_client.hget(name, "preferred_temperature")))
    
    return max_temperature

def housekeeping():
    print("Starting housekeeping")
    keys = redis_client.keys('person:*')
    for key in keys:
        timestamp = float(redis_client.hget(name, "timestamp"))
        if (datetime.now().timestamp() - timestamp) > MAX_AGE_STATUS:
            print("Deleting expired status for: %s" % key)
            redis_client.hdel(key)
            redis_client.srem("temps_at_home", key)

async def houskeeping_loop():
    while True:
        await asyncio.sleep(3600) # Run every hour
        housekeeping()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)