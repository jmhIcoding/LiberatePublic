__author__ = 'jmh081701'
from flask import  Flask
from flask import jsonify
from flask import request
import requests
app=Flask(__name__)
@app.route("/",methods=["GET"])
def getSimilarity():
    try:
        request_url = request.base_url()
        print(request_url)
        response =requests.get("http://127.0.0.0:56566"+request_url)
        return response
    except:
        return "Needed correct Json Request"

app.run(host="0.0.0.0",port=56565)