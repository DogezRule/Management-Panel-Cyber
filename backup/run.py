import os
from app import create_app

# Choose config class based on FLASK_ENV or APP_CONFIG env vars
config_object = os.getenv('APP_CONFIG')
if not config_object:
    env = os.getenv('FLASK_ENV', 'development').lower()
    if env == 'production':
        config_object = 'config.ProductionConfig'
    else:
        config_object = 'config.DevelopmentConfig'

app = create_app(config_object=config_object)

if __name__ == '__main__':
    debug = app.config.get('DEBUG', False)
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=debug)
