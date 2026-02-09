import os
import django
import json
from datetime import datetime

import sys
# Add the project root to sys.path so 'app' module can be found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from app.nexus.models import Trade

def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

trades = Trade.objects.all().order_by('-entry_time')
data = []
for t in trades:
    data.append({
        'id': t.id,
        'symbol': t.symbol,
        'type': t.type,
        'entry_time': t.entry_time,
        'entry_price': t.entry_price,
        'close_time': t.close_time,
        'close_price': t.close_price,
        'pnl': t.pnl,
        'closing_reason': t.closing_reason,
        'strategy': t.strategy
    })

print(json.dumps(data, default=serialize_datetime, indent=2))
