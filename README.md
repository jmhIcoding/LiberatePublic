# LiberateFull

This is Liberate, a tool that first automatically reverse-engineer the classifying methods used for traffic differentiation.
Then exploit different possible methods to evade being classified.

Only supports linux machine so far.

Before running:

* USE python 2.x!!!!!!!!! *

* Install Scapy http://www.secdev.org/projects/scapy/
```
pip2 install --pre scapy[basic]
```

* Install NetfilterQueue https://pypi.python.org/pypi/NetfilterQueue
```
apt-get install build-essential python-dev libnetfilter-queue-dev
pip2 install NetfliterQueue
```

* Install Wireshark and tshark

```
sudo apt-get install wireshark tshark
```

* Install Numpy1.6
```
pip2 install numpy==1.6
```

* Install tornado(For Server)

```
pip2 install tornado
```

* Install MySQLDB(For Server)
```
apt-get install mysql-server mysql-client libmysqlclient-dev
pip install MySQLdb-python
```
* Install other Software (For Server)
```
pip install matplotlib==2.2.3

```
You should set the mysql database connection string consistent with the parameters of your configs_local.cfg, such as dbUser,dbPassword,dbName

* Have your own replay server ready (different machine than the client machine in order for your traffic to travel through the tested network). Then in python_lib.py, add your own server name and IP address pair in the class Instance (e.g. server1 and 1.2.3.4).


```python
class Instance(object):
    def __init__(self):
        self.ips = {
                    'replay'            : '0.0.0.0',
                    'server1'         	: '1.2.3.4',
                   }
```

* Get record replay, you can record the network traffic yourself (using Wireshark) or use the replays provided here (e.g., traffic recorded when watching Youtube). Please remember to clean up the traffic (i.e., only leave the one connection that are of interest in the pcap file) if you would like to record traffic yourself for analysis. Example code of extracting only the traffic on port 80 from replay.pcap and storing into cleanedreplay.pcap.
```
tcpdump -r replay.pcap -w cleanedreplay.pcap port 80
```

* Parse the record replay. You need to parse the pcap file into file that can be loaded by the replay client and server. You also need to create the random (or bit inverted) replay for controlled experiment.
The first command is to parse the replay, and the second one is to create a replay file with all payload randomized. You can also create replay with bit inverted instead of randomizing the payload, for that, you need to use the parameters *'--randomPayload=True --invertBit=True'*.
```
python replay_paser.py --pcap_folder=/the/path/to/pcap
```

```
python replay_paser.py --pcap_folder=/the/path/to/pcap --randomPayload=True --pureRandom=True
```

* Determine what is the metrics used to determine differentiation. Some example metrics are 1. Whether the replay is blocked, using *replayResult* the return value from calling *replay_client*, its value is either 'Finish' or 'Block'. 2. Performance analysis, checking whether this replay shows different performance than the original replay (the first replay with unmodified traffic). 3. Use keyboard to type classification result. You can also supply you own method (i.e., get account info for zero-rating tests) to get more metrics. Modify the *runReplay* method in *ClassifierAnalysis.py* to determine the classification result of each replay from those metrics.

```python
def runReplay(PcapDirectory, replayName):
...
	# TODO Supplement YOUR OWN method to get the classification result here
	classification = the method of your choice
```
* If you choose to check whether the performance of the replays are the same, you need to uncomment the code that is in the *Beginning of asking the replay analyzer for performance difference* block in the *runReplay* method, the code there compares the performance of this replay against the original one. But remember you need to have a replay_analyzer running on the server in this case.

* Right now, the main analysis script (LiberateAnalysis.py) only does differentiation detection, reverse engineering and evasion evaluation. If you want to deploy the LiberateProxy with succeeded evasion technique after the previous analysis steps, please uncomment the *Step 4* block in the *main* method.

How to run:

On server side:

* First you need to provide the paths to the record replays into the folders.txt file. For example, make it a single line file with '/path/to/Youtube'

```
sudo python replay_analyzerServer.py --port=56565 --ConfigFile=configs_local.cfg &
sudo python replay_server.py --ConfigFile=configs_local.cfg 
```

* If you need performance analysis, you need a replay analyzer running at the same time, which will compare the throughput for each replay against the original replay to detect differentiation:

```
sudo python replay_analyzer.py --ConfigFile=configs_local.cfg 
```

On client side:
```
sudo python LiberateAnalysis.py --pcap_folder=/replays/Youtube --num_packets=1 --serverInstance=server1 
```

* The *pcap_folder* specifies where the replay traffic is. *num_packets* is the number of packets that you want to check for matching contents, for example, 1 means only randomizing the first packet to determine whether there are matching contents there. *serverInstance* is the server name that you supplied in python_lib.py.

* The replay record will be stored on your server in the result directory specified in the *configs_local.cfg* file, the default path is /data/.

* If *--doTCPDUMP=True* is provided as a parameter, each replay will also be saved in the results directory as a pcap file on the client.
