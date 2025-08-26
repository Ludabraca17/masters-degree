#this is a file for reading attributes of a device from thingsboard
import requests

def read_attribute(username, password, device_id, thingsboard_url, attribute_key):
    """
    This function reads the TB attribute from TB. The data read in this file is production order
    from "Virtual device" and signals from modules and AGVs (NodeRed1, NodeRed2, AGV).
    """

    # Client attributes to be read
    attributes_to_read = [attribute_key]  # Replace with the attributes you want to read
    #print("debug print - start of function")

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
            #print(f"Attribute {attribute_key} read successfully.")
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
            #print(f"JWT Token obtained: {token}")
            return token
        else:
            print(f"Failed to authenticate. Status Code: {response.status_code}, Response: {response.text}")
            return None

    # Main logic
    jwt_token = get_jwt_token()
    #print("jwt token obtained: ", jwt_token)
    if jwt_token:
        local_variable = read_client_attributes(jwt_token)[0]["value"]
        return local_variable



