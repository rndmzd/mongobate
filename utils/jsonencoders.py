from bson import ObjectId
import simplejson as json
from datetime import datetime


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (list, tuple)):
            return [self.default(item) for item in obj]
        if isinstance(obj, dict):
            return {key: self.default(value) for key, value in obj.items()}
        if hasattr(obj, "__dict__"):
            return self.default(obj.__dict__)
        return super().default(obj)
