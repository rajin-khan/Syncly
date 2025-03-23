import Database


db = Database().get_instance()
user = db.users_collection.find_one({"username": "luffy"})
print("User:", user)
print("Drives:", list(db.drives_collection.find({"user_id": user["_id"]})))
#eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJsdWZmeSIsImV4cCI6MTc0MjY0NDQzN30.ddy-epRpR3KAafgIIwKR564L_ei_HP6C_U2bZ25-8mE