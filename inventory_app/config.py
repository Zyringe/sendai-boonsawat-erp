import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Railway provides a persistent volume — set DATA_DIR env var to that mount path.
# Falls back to local instance/ folder for development.
_data_dir = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'instance'))
DATABASE_PATH = os.path.join(_data_dir, 'inventory.db')

LOW_STOCK_DEFAULT_THRESHOLD = 10
ITEMS_PER_PAGE = 50
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'imports')

# Override via Railway environment variables
SECRET_KEY     = os.environ.get('SECRET_KEY',     'sendai-boonsawat-erp-secret')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD',  'sendai12345')
