import json

from database.credentials import get_genlayer_db_connection


class DatabaseFunctions:

    def __init__(self):
        self.connection = get_genlayer_db_connection()
        self.cursor = self.connection.cursor()

    def close(self):
        self.cursor.close()
        self.connection.close()
    
    def validator_details(self, validator) -> dict:
        return {
            'id': validator[0],
            'address': validator[1],
            'stake': float(validator[2]),
            'provider': validator[3],
            'model': validator[4],
            'config': validator[5],
            'updated_at': validator[6].strftime("%m/%d/%Y, %H:%M:%S")
        }
    
    def transaction_audit_details(self, transaction_audit) -> dict:
        return {
            'id': transaction_audit[0],
            'transaction_id': transaction_audit[1],
            'status': transaction_audit[2],
            'transaction_data': transaction_audit[3],
            'created_at': transaction_audit[4].strftime("%m/%d/%Y, %H:%M:%S")
        }


    def create_validator(self, address:str, stake:int, provider:str, model:str, config:str):
        self.cursor.execute(
            "INSERT INTO current_state (id, data) VALUES (%s, %s);", (address, json.dumps({'stake':stake}))
        )
        self.cursor.execute(
            "INSERT INTO validators (address, stake, provider, model, config, created_at) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP);",
            (address, stake, provider, model, config),
        )
        self.connection.commit()
        return self.get_validator(address)

    def delete_validator(self, address:str):
        self.cursor.execute(
            "DELETE FROM validators WHERE address = %s;",
            (address,),
        )
        self.connection.commit()
        return {}

    def update_validator(self, validator_address:str, stake:float, provider:str, model:str, config:str):
        self.cursor.execute(
            "UPDATE validators SET stake = %s, provider = %s, model = %s, config = %s, created_at = CURRENT_TIMESTAMP WHERE address = %s;",
            (stake, provider, model, config, validator_address),
        )
        self.connection.commit()
        return self.get_validator(validator_address)

    def get_validator(self, address:str):
        self.cursor.execute("SELECT * FROM validators WHERE address = %s", (address,))
        self.connection.commit()
        validator = self.cursor.fetchone()
        if validator:
            return self.validator_details(validator)
        else:
            return {}

    def all_validators(self):
        self.cursor.execute("SELECT * FROM validators")
        self.connection.commit()
        validators = []
        for validator in self.cursor.fetchall():
            validators.append(self.validator_details(validator))
        return validators

    def insert_transaction_audit(self, transaction_id:int, status:str, transaction_data:str):
        self.cursor.execute(
            "INSERT INTO transactions_audit (transaction_id, status, transaction_data) VALUES (%s, %s, %s);",
            (transaction_id, status, transaction_data),
        )
        self.connection.commit()
        return self.get_transaction_audit(transaction_id)

    def get_transaction_audit(self, transaction_id:int):
        self.cursor.execute("SELECT * FROM transactions_audit WHERE transaction_id = %s", (transaction_id,))
        self.connection.commit()
        audit_entries = []
        for audit in self.cursor.fetchall():
            audit_entries.append(self.transaction_audit_details(audit))
        return audit_entries

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
