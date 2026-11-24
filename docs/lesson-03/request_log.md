I received the 401 area code because I messed with the authentication bearer portion of the request, which broke the authentication and made it so HubSpot did not know who I was and I was not authenticated. And then I got the 404 error code because I changed the number of the contact ID.

So I asked for something that HubSpot could not find even though it knew who I was. Then the 403 error code I got because I changed the contact to company.

So I was asking for something that did exist and I was properly authenticated in and so I knew who I was. But my service key did not give me access to view that information.

When you send calls all at the same time, they can potentially arrive out of order to the server because they're racing each other instead of going one after another

When simulating a 429 error code. The 19 calls per second limit was not enforced by the HubSpot server, instead the 190 over 10 seconds is the one that tripped the 429 error code. Even though it said the the limit was 19 calls per second it still allowed more than that.

200 - This means that the API request to the server was successful.
401 - This means that the request was not properly authenticated
403 - Means that you are properly authenticated but do not have the permissions to access the information requested
404 - This means that you were properly authenticated but the server could not find any information correlating to your request
429 - This means that your request was authenticated and valid but you reached the rate limit and sent too many requests for the server to be able to handle in a set period of time

Added in a prompt to Claude code that trimmed any white space before or after the first and last name in the HubSpot contact page so that it printed cleanly