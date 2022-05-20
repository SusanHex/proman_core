# this file is for the prebuilt actions and should be used as a reference to create more


async def basic_rest_request(
    data: str, url: str, method: str = "GET", scheme: str = "<data>"
):
    """Sends a rest request to URL using MEtHOD. Will replace '<data>'
    with the provided data.

    Args:
        data (str): The data to send
        url (str): The URL of the rest endpoint
        method (str, optional): The HTTP method to use. (GET, POST, etc).
        Defaults to "GET".
        scheme (str, optional): The data to send in the payload of the rest request.
        Defaults to "<data>".
    """
    pass
