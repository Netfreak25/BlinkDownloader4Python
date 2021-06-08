import requests
import shutil
import os
import sys
import json
import time
from datetime import datetime
import pytz
import os.path
import pickle
import getpass

blinkAPIServer = 'rest-prod.immedia-semi.com'
sleepingTime = 30

def saveSession(data):
    (authToken, accountID, userID, clientID, region) = data
    file = open('data.pkl', 'w')
    pickle.dump(data, file)
    file.close()

def loadSession():
    file = open('data.pkl')
    data = pickle.load(file)
    return data

def saveConfig(data):
    (username, password, SaveFolder) = data
    file = open('config.pkl', 'w')
    pickle.dump(data, file)
    file.close()

def loadConfig():
    file = open('config.pkl')
    data = pickle.load(file)
    return data

def verifyToken():
    try:
        (authToken, accountID, userID, clientID, region) = loadSession()

        headers = {
            'TOKEN_AUTH': authToken,
        }
        uri = 'https://rest-'+ region +".immedia-semi.com/api/v1/camera/usage"
        sync_units = requests.get(uri, headers=headers)
        networks = sync_units.json()
        networkID = networks["networks"][0]["network_id"]
        return(authToken, accountID, userID, clientID, region)
    except Exception, e:
        return (0, 0, 0, 0, 0)

(authToken, accountID, userID, clientID, region) = verifyToken()

if ( str(authToken) != "0" ):
    print("Old session still valid, skipping login")
    (username, password, SaveFolder) = loadConfig()
else:
    try:
        (username, password, SaveFolder) = loadConfig()
        print("Using stored credentials to log in")

    except Exception:
        username = str(raw_input("Email Address: "))
        password = str(getpass.getpass("Password: "))
        SaveFolder = str(raw_input("Save Folder [/tmp/Blink]: "))

        if ( SaveFolder.strip() == "" ):
            SaveFolder = "/tmp/Blink"
        print("Using " + str(SaveFolder) + " as folder to store the videos")
            
    headers = {
        'Host': blinkAPIServer,
        'Content-Type': 'application/json',
    }
    
    body = {
        'password': password,
        'email': username,
        'unique_id': '00000000-1111-0000-1111-00000000005'
    }

    body = json.dumps(body)
    uri = 'https://'+ blinkAPIServer +'/api/v5/account/login'
    res = requests.post(uri, headers=headers, data=body)

    try:
        authToken = res.json()["auth"]["token"]
        region = res.json()["account"]["tier"]
        accountID = res.json()["account"]["account_id"]
        userID = res.json()["account"]["user_id"]
        clientID = res.json()["account"]["client_id"]
        print('Authenticated with Blink successfully. Please check your email or SMS/Text on your phone for the pin.')

        data = (authToken, accountID, userID, clientID, region)
        saveSession(data)
        saveConfig((username, password, SaveFolder))
        print("Credentials and session saved for later")
    except Exception:
        print('Invalid credentials provided. Please verify email and password.')
        sys.exit()

    pin = input("Input PIN: ")
    pinuri = 'https://rest-'+ str(region) +".immedia-semi.com/api/v4/account/"+ str(accountID) +'/client/'+ str(clientID) +"/pin/verify"
    pin_headers = {
       "CONTENT-TYPE": "application/json",
       "TOKEN-AUTH": authToken,
    }
    pin_body = {
        "pin": str(pin),
    }

    pin_body = json.dumps(pin_body)

    # Added try/catch to catch the invalid pin
    try:
        pin_response = requests.post(pinuri, headers=pin_headers, data=pin_body)
    except Exception:
        print("Invalid Pin response. Please re-run the script again and use the same pin within the first minute.")
        sys.exit()

# Check if SaveFolder exists
def createFolder(foldername):
    if not os.path.isdir(foldername):
        os.makedirs(foldername)

createFolder(SaveFolder)

headers = {
    'TOKEN_AUTH': authToken,
}

uri = 'https://rest-'+ region +".immedia-semi.com/api/v1/camera/usage"
sync_units = requests.get(uri, headers=headers)
networks = sync_units.json()["networks"]

while True:
    for sync_unit in networks:
        networkID = sync_unit["network_id"]
        networkName = sync_unit["name"]
        path = SaveFolder + "/" + networkName
        createFolder(path)
        for camera in sync_unit["cameras"]:
            cameraName = camera["name"]
            cameraId = camera["id"]
            cam_uri = 'https://rest-'+ str(region) +'.immedia-semi.com/network/'+ str(networkID) +'/camera/' + str(cameraId)
            cam = requests.get(cam_uri, headers=headers)
            cam = cam.json()
            camThumbnail = cam["camera_status"]["thumbnail"]

            # create download folder
            path = SaveFolder + "/" + networkName + "/" + cameraName
            createFolder(path)

            #Download camera thumbnail
            thumbURL = 'https://rest-'+ region +'.immedia-semi.com' + camThumbnail + ".jpg"
            thumbPath = path+"/" + "thumbnail_" + camThumbnail.split("/")[-1] + ".jpg"

            #Skip if already downloaded
            if not (os.path.isfile(thumbPath)):
                    print("Downloading thumbnail for " + cameraName + " camera in " + networkName + ".")
                    res = requests.get(thumbURL, headers=headers)
                    open(thumbPath, 'wb').write(res.content)

    newVideo = False
    pageNum = 1

    while True:
        uri = 'https://rest-'+ str(region) +'.immedia-semi.com/api/v1/accounts/'+ str(accountID) +'/media/changed?since=2015-04-19T23:11:20+0000&page=' + str(pageNum)
        
        # Get the list of video clip information from each page from Blink
        response = requests.get(uri, headers=headers)
        response = response.json()
        path = SaveFolder + "/" + networkName + "/" + cameraName

        # quit if no more media is available to download
        try:
            media = response["media"]
            if ( media == []):
                break
        except Exception:
            break

        for video in media:
            #Video Clip information
            address = video["media"]
            timestamp = video["created_at"]
            network = video["network_name"]
            camera = video["device_name"]
            camera_id = video["device_id"]
            deleted = video["deleted"]

            #Skip if marked as deleted
            if(str(deleted) == "True"):
                continue

            # Download address of video clip
            videoURL = 'https://rest-'+ str(region) +'.immedia-semi.com' + str(address)
            videoPath = path + "/" + str(timestamp) + ".mp4"

            # Download video if it is new
            if not (os.path.isfile(videoPath)):
                download = requests.get(videoURL, headers=headers)
                statusCode = download.status_code
                if (statusCode != "200"):
                    newVideo = True
                    print("Downloading " + str(timestamp) + ".mp4")
                    open(videoPath, 'wb').write(download.content)
                else:
                    print("Download failed - Error " + str(statusCode))
        pageNum += 1

    if newVideo:
         print("All new videos and thumbnails downloaded to " + SaveFolder)
         print("Sleeping for " + str(sleepingTime) + " minutes before next run...")
    else:
         print("No new Data - Sleeping for " + str(sleepingTime) + " minutes before next run...")

    time.sleep(60 * sleepingTime)


