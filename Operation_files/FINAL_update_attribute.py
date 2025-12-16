#this is a file for writing attributes on a device on thingsboard

import requests

def update_attribute(username: int, 
                    password: int, 
                    device_id: int, 
                    thingsboard_url: int, 
                    attribute_key: int, 
                    attribute_value: int) -> None:
    """
    Function updates a specific attribute on a ThingsBoard device.
    
    This function updates the TB attribute on TB. It utilizes the REST API of ThingsBoard. 
    It can be used for updating current state of the order (times, positions, etc.) as well as 
    current states of modules and AGVs ("idle", "callibrating", "processing", "error") and their command messages.

    Args:
        username (int): Username of the TB user.
        password (int): Password of the TB user.
        device_id (int): ID of the device from which the attribute is to be read.
        thingsboard_url (int): URL of the ThingsBoard instance.
        attribute_key (int): Key of the attribute to be read.
        attribute_value (int): Value which we want to set for the attribute.
    """

    def update_shared_attributes(jwt_token):
        url = f"{thingsboard_url}/api/plugins/telemetry/DEVICE/{device_id}/attributes/SHARED_SCOPE"
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {jwt_token}"
        }
        payload = {
            attribute_key: attribute_value
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            pass
        else:
            print(f"Failed to update attributes. Status Code: {response.status_code}, Response: {response.text}")

    def get_jwt_token():
        """
        This function is used for fetching a jwt token from TB. It is used for authentication of the user.
        """
        url = f"{thingsboard_url}/api/auth/login"
        payload = {
            "username": username,
            "password": password
        }
        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            token = response.json().get("token")
            return token
        else:
            print(f"Failed to authenticate. Status Code: {response.status_code}, Response: {response.text}")
            return None

    # Main logic
    jwt_token = get_jwt_token()
    if jwt_token:
        update_shared_attributes(jwt_token)