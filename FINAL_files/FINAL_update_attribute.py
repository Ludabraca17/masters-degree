#this is a file for writing attributes on a device on thingsboard

import requests

def update_attribute(username, password, device_id, thingsboard_url, attribute_key, attribute_value):
    """
    This function updates the TB attribute on TB. It can be used for updating current state of the order (times,
    positions, etc.) as well as current states of modules and AGVs ("idle", "callibrating", "processing", "error")
    and their command messages.
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

        #print(f"Updating attributes with payload: {payload}")
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            #print("Attributes updated successfully.")
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
            #print(f"JWT Token obtained: {token}")
            return token
        else:
            print(f"Failed to authenticate. Status Code: {response.status_code}, Response: {response.text}")
            return None

    # Main logic
    jwt_token = get_jwt_token()
    if jwt_token:
        update_shared_attributes(jwt_token)