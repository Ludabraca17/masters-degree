#this is a file for reading attributes of a device from thingsboard
import requests

def read_attribute(username: int, 
                    password: int, 
                    device_id: int, 
                    thingsboard_url: int, 
                    attribute_key: int, 
                    return_ts=False) -> dict:
    """
    Function reads a specific attribute from a ThingsBoard device.
    
    This function reads the TB attribute from TB. It utilizes the REST API of ThingsBoard. Inputs are presented below. It returns
    the value of the attribute key provided in the input.

    Args:
        username (int): Username of the TB user.
        password (int): Password of the TB user.
        device_id (int): ID of the device from which the attribute is to be read.
        thingsboard_url (int): URL of the ThingsBoard instance.
        attribute_key (int): Key of the attribute to be read.
        return_ts (bool, optional): If True, returns the timestamp along with the value. Defaults to False.

    Returns:
        dict: Dictionary containing the attribute value, and optionally the timestamp.
    """
    # Client attributes to be read
    attributes_to_read = [attribute_key]  # Replace with the attributes you want to read

    def read_client_attributes(jwt_token):
        url = f"{thingsboard_url}/api/plugins/telemetry/DEVICE/{device_id}/values/attributes"
        headers = {
            "X-Authorization": f"Bearer {jwt_token}"
        }
        # Request parameters
        params = {
            "keys": ",".join(attributes_to_read)
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to read attributes. Status Code: {response.status_code}, Response: {response.text}")

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
        resp = read_client_attributes(jwt_token)
        item = resp[0] if resp else {"value": {}, "lastUpdateTs": None}
        return item["value"] if not return_ts else {"value": item["value"], "ts": item.get("lastUpdateTs")}



