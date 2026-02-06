import logging
import os
from flask import Flask
from dotenv import load_dotenv
import MetaTrader5 as mt5
from flasgger import Swagger
from werkzeug.middleware.proxy_fix import ProxyFix
from swagger import swagger_config

# Import routes
from routes.health import health_bp
from routes.symbol import symbol_bp
from routes.data import data_bp
from routes.position import position_bp
from routes.order import order_bp
from routes.history import history_bp
from routes.error import error_bp

load_dotenv()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'

swagger = Swagger(app, config=swagger_config)

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(symbol_bp)
app.register_blueprint(data_bp)
app.register_blueprint(position_bp)
app.register_blueprint(order_bp)
app.register_blueprint(history_bp)
app.register_blueprint(error_bp)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

if __name__ == '__main__':
    # Try to initialize MT5 multiple times
    # Try to initialize MT5 multiple times with explicit path
    mt5_path = "C:/Program Files/MetaTrader 5/terminal64.exe"
    for i in range(5):
        if mt5.initialize(path=mt5_path):
            logger.info("MT5 initialized successfully.")
            break
        else:
            logger.error(f"Failed to initialize MT5 (Attempt {i+1}/5). Path: {mt5_path}, Error: {mt5.last_error()}")
            if i < 4:
                import time
                time.sleep(5)
    
    app.run(host='0.0.0.0', port=int(os.environ.get('MT5_API_PORT', 5001)))