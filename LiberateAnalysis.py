import threading, sys, pickle, time, subprocess, os, socket,datetime, numpy, replay_client, LiberateProxy, urllib2, urllib
from python_lib import *
from collections import deque

'''
This is the main script for liberate
It will
1. Check whether there is differentiation
2. Reverse engineer the classification rule
3. Enumerate the evasion techniques with liberate proxy
4. Running the liberate proxy with effective technique
'''

Replaycounter = 0

class AnalyzerI(object):
    '''
    This class contains all the methods to interact with the analyzerServer
    '''
    def __init__(self, ip, port):
        self.path = ('http://'
                     + ip
                     + ':'
                     + str(port)
                     + '/Results')


    def ask4analysis(self, id, historyCount, testID):
        '''
        Send a POST request to tell analyzer server to analyze results for a (userID, historyCount)

        server will send back 'True' if it could successfully schedule the job. It will
        return 'False' otherwise.

        This is how and example request look like:
            method: POST
            url:    http://54.160.198.73:56565/Results
            data:   userID=KSiZr4RAqA&command=analyze&historyCount=9
        '''
        # testID specifies the test number in this series of tests
        # testID = 0 is the first replay in this series of tests, thus it is the baseline (original) to be compared with
        data = {'userID':id, 'command':'analyze', 'historyCount':historyCount, 'testID':testID}
        res = self.sendRequest('POST', data=data)
        return res

    def getSingleResult(self, id, historyCount, testID):
        '''
        Send a GET request to get result for a historyCount and testID

        This is how an example url looks like:
            method: GET
            http://54.160.198.73:56565/Results?userID=KSiZr4RAqA&command=singleResult&historyCount=9
        '''
        # testID specifies the test number in this series of tests
        data = {'userID':id, 'command':'singleResult', 'testID':testID}

        if isinstance(historyCount,int):
            data['historyCount'] = historyCount

        res = self.sendRequest('GET', data=data)
        return res

    def sendRequest(self, method, data=''):
        '''
        Sends a single request to analyzer server
        '''
        data = urllib.urlencode(data)

        if method.upper() == 'GET':
            req = urllib2.Request(self.path + '?' + data)

        elif method.upper() == 'POST':
            req  = urllib2.Request(self.path, data)

        res = urllib2.urlopen(req).read()
        print '\r\n RESULTS',res
        return json.loads(res)

def processResult(result):
    # Only if ks2ratio > ks2Beta (this is the confidence interval) the ks2 result is trusted, otherwise only the area test is used
    # Default suggestion: areaThreshold 0.1, ks2Beta 95%, ks2Threshold 0.05
    # KS2:
    # ks2Threshold is the threshold for p value in the KS2 test, if p greater than it, then we cannot
    # reject the hypothesis that the distributions of the two samples are the same
    # If ks2pvalue suggests rejection (i.e., p < ks2Threshold), where accept rate > (1 - ks2Beta), the two distributions are not the same (i.e., differentiation)
    # Else, the two distributions are the same, i.e., no differentiation
    # Area:
    # if area_test > areaThreshold, the two distributions are not the same (i.e., Differentiation)
    # Else, the two distributions are the same, i.e., no differentiation
    # Return result score, 0  : both suggests no differentiation
    #                      1  : inconclusive conclusion from two methods (Considered as no differentiation so far)
    #                      2  : both suggests differentiation
    #                      if target trace has less throughput, return negative value respectively, e.g., -1 means target trace is throttled
    #        result rate: differentiated rate = (normal - throttled)/throttled

    areaT = Configs().get('areaThreshold')
    ks2Beta  = Configs().get('ks2Beta')
    ks2T  = Configs().get('ks2Threshold')

    ks2Ratio = float(result['ks2_ratio_test'])
    ks2Result = float(result['ks2pVal'])
    areaResult = float(result['area_test'])

    # ks2_ratio test is problematic, sometimes does not give the correct result even in the obvious cases, not using it so far
    # 1.Area test passes and 2.With confidence level ks2Beta that the two distributions are the same
    # Then there is no differentiation
    if (areaResult < areaT) and (ks2Result > ks2T):
        outres = 0
    # 1.Area test does not pass and 2.With confidence level ks2Beta that the two distributions are not the same
    # Then there is differentiation
    elif (areaResult > areaT) and (ks2Result < ks2T):
        outres = 2
        # rate = (result['xput_avg_test'] - result['xput_avg_original'])/min(result['xput_avg_original'], result['xput_avg_test'])
    # Else inconclusive
    else:
        outres = 1
        PRINT_ACTION('##### INConclusive Result, area test is' + str(areaResult) + 'ks2 test is ' + str(ks2Result), 0)
        # rate = (result['xput_avg_test'] - result['xput_avg_original'])/min(result['xput_avg_original'], result['xput_avg_test'])

    return outres

def GetMeta(PcapDirectory, numPackets, client_ip):

    Meta = {'Client':[], 'Server':[]}
    changeMeta = {'Client':[], 'Server':[]}

    # The default pickleFile name
    picklesFile = 'test.pcap_server_all.pickle'
    picklecFile = 'test.pcap_client_all.pickle'

    for file in os.listdir(PcapDirectory):
        if file.endswith(".pcap_server_all.pickle"):
            picklesFile = file
        elif file.endswith(".pcap_client_all.pickle"):
            picklecFile = file

    serverQ, tmpLUT, tmpgetLUT, udpServers, tcpServerPorts, replayName = \
        pickle.load(open(PcapDirectory + picklesFile,'r'))

    clientQ, udpClientPorts, tcpCSPs, replayName = \
        pickle.load(open(PcapDirectory + picklecFile, 'r'))

    # There should always be at least one client packet
    if len(clientQ) > 0:
        for cPacket in clientQ:
            Meta['Client'].append(len(cPacket.payload.decode('hex')))

    # There should only be one protocol that is in the pcap
    # Thus the one with an csp in it
    Prot = 'tcp'
    print(serverQ)
    for P in serverQ.keys():
        if serverQ[P] != {}:
            Prot = P
    # There should only be a single csp as well
    csp = serverQ[Prot].keys()[0]

    if len(serverQ) > 0:
        # For UDP traffic
        if Prot == 'udp':
            for sPacket in serverQ[Prot][csp]:
                Meta['Server'].append(len(sPacket.payload.decode('hex')))

        else:
            for sPacket in serverQ[Prot][csp]:
                Meta['Server'].append(len(sPacket.response_list[0].payload.decode('hex')))

    # Now we need to filter out the packets that we are going to investigate
    packetMeta = os.path.abspath(PcapDirectory + '/' + 'packetMeta')
    with open(packetMeta, 'r') as f:
        # We need to check how many client packets and server packets are in the first numPackets packets
        count = 0
        clientc = 0
        serverc = 0
        for line in f:
            l = line.replace('\n', '').split('\t')
            srcIP     = l[5]
            if client_ip == srcIP:
                clientc += 1
            else:
                serverc +=1
            count += 1
            # We only need to make changes in the first numPackets packets
            if count == numPackets:
                break

    changeMeta['Client'] = Meta['Client'][:clientc]
    changeMeta['Server'] = Meta['Server'][:serverc]

    return changeMeta,csp,Prot, replayName, clientQ, serverQ

# This function would run replay client against the replay server for one time
# The tricky part is to get the classification result, the method now is to write into the 'Result.txt' file

def runReplay(PcapDirectory, pacmodify, analyzerI, libProxy=None):

    global Replaycounter

    cmpacNum = -1
    caction = None
    cspec = None
    smpacNum = -1
    saction = None
    sspec = None

    classification = None

    Side, Num, Action, Mspec = pickle.loads(pacmodify)

    if Side == 'Client':
        cmpacNum = Num
        caction = Action
        cspec = Mspec
    elif Side == 'Server':
        smpacNum = Num
        saction = Action
        sspec = Mspec

    configs = Configs()

    try:
        replayResult = replay_client.run(configs = configs, libProxy=libProxy, pcapdir = PcapDirectory, cmpacNum = cmpacNum, caction = caction, cspec = cspec,
                          smpacNum = smpacNum, saction = saction, sspec = sspec)
    except:
        print '\r\n Error when running replay'
        replayResult = 'Error'

    # print '\r\n Whether Finished', replayResult

    classification = replayResult

    print '\r\n CLASSIFIED AS ', classification
    # The period for extracting the classification results
    time.sleep(15)

    # ASK the replay analyzer for throughput analysis result
    permaData = PermaData()
    PRINT_ACTION('Fetching analysis result from the analyzer server',0)
    res = analyzerI.getSingleResult(permaData.id, permaData.historyCount, configs.get('testID'))

    # Check whether results are successfully fetched


    if res['success'] == True:
        # Process result here
        pres = processResult(res['response'])
        if pres == 1:
            PRINT_ACTION('INConclusive Result. Considered as NOT different from Original replay', 0)
            classification = 'Original'
        elif pres == 2:
            PRINT_ACTION('Different from Original replay', 0)
            classification = 'NotOriginal'
        else:
            PRINT_ACTION('NOT Different from Original replay', 0)
            classification = 'Original'
    else:
        # Only use whether the replayResult as classification
        PRINT_ACTION('\r\n Failed in fetching result ' + res['error'], 0)
        classification = replayResult

    # TODO Supplement YOUR OWN method to get the classification result here

    # Use the replayResult when testing censorship

    # OR Manually type what this traffic is classified as
    # classify_result = raw_input('Is it classified the same as original replay? "YES" or "NO"?')



    return classification

# This function looks into the regions in question one by one
# Each suspect region only has less than 4 bytes, filtered by the previous process
def detailAnalysis(PcapDirectory, Side, PacketNum, Length, original, analysisRegion, analyzerI):
    LeftB = analysisRegion[0][0]
    RightB = analysisRegion[0][1]
    Masked = analysisRegion[1]
    noEffect = []
    hasEffect = []
    for num in xrange(RightB - LeftB):
        newMask = list(Masked)
        newMask.append((LeftB+num,LeftB+num+1))
        pacmodify = pickle.dumps((Side, PacketNum, 'ReplaceI', newMask))
        Classi = Replay(PcapDirectory, pacmodify, analyzerI)
        if Classi == original:
            noEffect.append(LeftB+num)
        else:
            hasEffect.append(LeftB+num)

    return hasEffect


# RPanalysis stands for Random Payload analysis, which does the binary randomization to locate the matching contents
# It would return the key regions by randomizing different part of the payload
# The key regions are the regions that trigger the classification
def RPanalysis(PcapDirectory, Side, PacketNum, Length, original):
    allRegions = []
    # RAque is the queue that stores the analysis that are needed to run
    # each element of the queue is a pair of a. (pair of int) and b. (list of pairs): ((x,y),[(a,b),(c,d)])
    # (x,y) is the suspected region, meaning somewhere in this region triggers the classification
    # [(a,b),(c,d)] is the list of regions that we know does not have effect, so those region would be randomized
    # We would randomize half of the bytes in (x,y), and enqueue the new region based on the result of replaying both halves
    RAque = deque()
    # Initialization
    RAque.append(((0,Length),[]))
    analysis = RAque.popleft()
    # While the length of each suspected region is longer than 4, we need to keep doing the binary randomization
    while analysis[0][1] - analysis[0][0] > 4:
        LeftBar = analysis[0][0]
        RightBar = analysis[0][1]
        MidPoint = LeftBar + (RightBar - LeftBar)/2
        MaskedRegions = analysis[1]
        LeftMask = list(MaskedRegions)
        RightMask = list(MaskedRegions)
        LeftMask.append((LeftBar, MidPoint))
        RightMask.append((MidPoint, RightBar))

        # print '\n\t  PREPARING LEFT MASK',MaskedRegions,LeftMask
        lpacmodify = pickle.dumps((Side, PacketNum, 'ReplaceR', LeftMask))
        LeftClass = Replay(PcapDirectory, lpacmodify)
        # print '\n\t  PREPARING RIGHT MASK',MaskedRegions,RightMask
        rpacmodify = pickle.dumps((Side, PacketNum, 'ReplaceR', RightMask))
        RightClass = Replay(PcapDirectory, rpacmodify)
        # Four different cases
        if LeftClass == original and RightClass != original:
            RAque.append(((MidPoint, RightBar), LeftMask))

        elif LeftClass != original and RightClass == original:
            RAque.append(((LeftBar, MidPoint), RightMask))

        elif LeftClass != original and RightClass != original:
            RAque.append(((LeftBar,MidPoint), MaskedRegions))
            RAque.append(((MidPoint,RightBar), MaskedRegions))

        else:
            allRegions = ['Both sides have no effect']
            break

        analysis = RAque.popleft()

    if allRegions != []:
        return allRegions

    else:
        # Put the last poped element back
        RAque.appendleft(analysis)

        for region in RAque:
            effectRegion = detailAnalysis(PcapDirectory, Side, PacketNum, Length, original, region)
            allRegions.append(effectRegion)

    return allRegions


# This function inform the server to get ready for another replay
# The last parameter specifies whether we need to bring up the liberate proxy for this replay
def Replay(PcapDirectory, pacmodify, analyzerI = None, libProxy = None):
    global Replaycounter
    Replaycounter += 1
    # Repeat the experiment for 10 times, until we get a classification result, otherwise just
    classification = None
    for i in xrange(10):
        classification = runReplay(PcapDirectory, pacmodify, analyzerI, libProxy)
        time.sleep(10)
        if classification != None:
            break
        if i == 9:
            print "\r\n Can not get the classification result after the 10th trial, exiting"
            sys.exit()

    return classification



# This would do a full analysis on one side of the conversation
# Look into the payload by binary randomization
# If the key regions can be found in the payload
#    record those regions
def FullAnalysis(PcapDirectory, meta, Classi_Origin, Side, analyzerI):
    Analysis = {}
    for packetNum in xrange(len(meta[Side])):
        Analysis[packetNum] = []
        regions = []
        # Do Binary Randomization
        pacmodify = pickle.dumps((Side, packetNum + 1, 'Random', []))
        RClass = Replay(PcapDirectory, pacmodify,analyzerI)
        if RClass != Classi_Origin:
            regions = RPanalysis(PcapDirectory, Side, packetNum + 1, meta[Side][packetNum],Classi_Origin)
        if regions == []:
            RPresult = 'Random the whole packet does not change classification'
        else:
            RPresult = ['DPI based differentiation, matching regions:', regions]
        Analysis[packetNum] = RPresult

    return Analysis

# Iteratively prepend more packets with maximum length and check whether the classification changes
# After determine the number of packets n that are needed to prepend
# Prepend n packets with 1 byte of data, check whether the length of the packets matter
def PrependAnalysis(PcapDirectory, Classi_Origin, Side, Protocol, analyzerI):
    # n is the number of packets to prepend
    # l is the length of the prepended packets
    n = 0
    l = 1000
    # At most prepend 10 packets
    for i in xrange(10):
        # Prepend packets with 1000 bytes of data
        pacmodify = pickle.dumps((Side, 1, 'Prepend', [i + 1, 1000]))
        RClass = Replay(PcapDirectory, pacmodify, analyzerI)
        if RClass != Classi_Origin:
            n = i + 1
            print '\n\r After prepending',n ,' 1000 bytes packets, the classification Changed'
            break

    # Prepend n packets with 1 byte of data
    if n != 0:
        pacmodify = pickle.dumps((Side, 1, 'Prepend', [n, 1]))
        RClass = Replay(PcapDirectory, pacmodify, analyzerI)
        if RClass != Classi_Origin:
            print '\n\r After prepending',n ,' 1 bytes packets, the classification Changed'
            l = 1

    # Return the number of prepend packets and the payload of those packets needed to break the classification
    return n,l


# Get the flow info into a list
# e.g. [c0,c1,s0] means the whole flow contains 2 client packet and 1 server packet
def extractMetaList(meta):
    FullList = []
    for cnt in xrange(len(meta['Client'])):
        FullList.append('c'+str(cnt))
    for cnt in xrange(len(meta['Server'])):
        FullList.append('s'+str(cnt))

    return FullList


# For the lists inside, if the two consecutive lists contain memebers that are consecutive, we combine them together
# For example, [1,2], [3,4,5], [7,8]
# Would become [1,2,3,4,5], [7,8]
def CompressLists(Alists):
    lastNum = 0
    CompressedLists = []
    for Alist in Alists:
        if Alist[0] == (lastNum + 1):
            lastList = CompressedLists.pop(-1)
            CompressedLists.append(lastList + Alist)
            lastNum = Alist[-1]
        else:
            CompressedLists.append(Alist)
            lastNum = Alist[-1]
    return CompressedLists


# The Meta is used for printing out and easy to understand
# We need to have a compressed version of meta, which contains only the packet number and region blocks for parser to look for
def CompressMeta(Meta):
    CMeta = {}
    for packetNum in Meta:
        decision = Meta[packetNum]
        # If the payload of this packet is used by DPI
        if 'DPI' in decision[0]:
            CompressedLists = CompressLists(decision[1])
            CMeta[packetNum] = CompressedLists
        # Else, do not change anything
        else:
            CMeta[packetNum] = Meta[packetNum]
    return CMeta

def ExtractKeywordServer(clientport, serverQ, Prot, ServerAnalysis):
    for P in serverQ.keys():
        if serverQ[P] != {}:
            Prot = P
    csp = serverQ[Prot].keys()[0]
    sMeta = CompressMeta(ServerAnalysis)
    # Get the keywords that are being matched on
    MatchingPackets = {}
    for Pnum in sMeta:
        keywords = []
        fields = []
        field = 'NotHTTP'
        for Alist in sMeta[Pnum]:
            start = Alist[0]
            end = Alist[-1] + 1
            # We get the keyword from each sub field
            if Prot == 'udp':
                response_text = serverQ[Prot][csp][Pnum].payload.decode('hex')
                keyword = response_text[start : end]
            else:
                response_text = serverQ[Prot][csp][Pnum].response_list[0].payload.decode('hex')
                keyword = serverQ[Prot][csp][Pnum].response_list[0].payload.decode('hex')[start : end]
                if clientport == '00080':
                    e = end
                    s = start
                    for i in xrange(end, len(response_text) - 1):
                        if response_text[i: i + 2] == '\r\n':
                            e = i
                            break

                    for j in xrange(start, 1, -1):
                        if response_text[j - 2: j] == '\r\n':
                            s = j
                            break

                    if s != 1 and e != len(response_text) - 1:
                        fullheader = response_text[s:e]
                        field = fullheader.split(' ')[0]
            # keywords contains all the keywords matched in this packet
            keywords.append(keyword)
            fields.append(field)
        MatchingPackets[Pnum] = {'fields': fields, 'keywords' : keywords}

    return MatchingPackets

# Extract the corresponding contents for the matching bytes
def ExtractKeywordClient(clientport, clientQ, ClientAnalysis):
    cMeta = CompressMeta(ClientAnalysis)
    # Get the keywords that are being matched on
    MatchingPackets = {}
    for Pnum in cMeta:
        keywords = []
        fields = []
        for Alist in cMeta[Pnum]:
            start = Alist[0]
            end = Alist[-1] + 1
            # We get the keyword from each sub field
            request_text = clientQ[Pnum].payload.decode('hex')
            keyword = request_text[start : end]
            field = 'NotHTTP'
            if clientport == '00080':
                e = end
                s = start
                for i in xrange(end, len(request_text) - 1):
                    if request_text[i : i + 2] == '\r\n':
                        e = i
                        break

                for j in xrange(start, 1, -1):
                    if request_text[j - 2 : j] == '\r\n':
                        s = j
                        break

                if s != 1 and e != len(request_text) - 1:
                    fullheader = request_text[s:e]
                    field = fullheader.split(' ')[0]

            # keywords contains all the keywords matched in this packet
            keywords.append(keyword)
            fields.append(field)
        MatchingPackets[Pnum] = {'fields': fields, 'keywords' : keywords}
    # We return a dictionary of packet to keywords and fields
    # e.g. MatchingPackets = {0: {'keywords': ['GET ', '\r\nHost:', 'nflx'], 'fields': ['GET', '\r\nHost:', 'Host:']}}
    # The matching contents in packet 0 are 'GET' '\r\nHost:' 'nflx', they are in the fields 'GET', '\r\nHost:' and 'Host:' respectively
    # We can see the last keyword 'nflx' is mapped to a HTTP header.
    # For connection other than HTTP, the fields will be 'NotHTTP'

    return MatchingPackets

# Probe the location of the middlebox
# By making the matching packet TTL limited
# We would append same number of packets (with random payload) after the matching packets
# The appended ones would reach the server while TTL-limited can not
# Note that the replay server will reply to packet with the expected length
def GetTTL(PcapDirectory, Classi_Origin, Keywords, Protocol, PreNum, PreLen, AnalyzerI):
    for ttl in range(1, 64):
        p = LiberateProxy.LiberateProxy(Keywords, 'TTLP', Protocol, PreLen, PreNum, ttl, 30)
        # No need to modify the payload for the replay
        nomodify = pickle.dumps(('Client', -1, None, None))
        EClass = Replay(PcapDirectory, nomodify, AnalyzerI, p)
        # If the classification result is the original one, the ttl limited matching packet has reached the classifier
        if EClass == Classi_Origin:
            return ttl
    return None

def setUpConfig(configs):
    configs.set('ask4analysis'     , False)
    configs.set('analyzerPort'     , 56565)
    configs.set('byExternal', True)
    configs.set('testID', '-1')
    configs.set('areaThreshold', 0.1)
    configs.set('ks2Threshold', 0.05)
    configs.set('ks2Beta', 0.95)

    configs.read_args(sys.argv)
    return configs

def main(args):

    # injectionCodes are the modifications we can use for injection
    injectionCodes = {}
    IPinjectionCodes = ['IPi1','IPi2','IPi3','IPi4','IPi5','IPi6','IPi7','IPi8','IPi9']
    injectionCodes['tcp'] = IPinjectionCodes + ['TCPi1','TCPi2','TCPi3','TCPi4','TCPi5']
    injectionCodes['udp'] = IPinjectionCodes + ['UDPi1','UDPi2','UDPi3']
    # splitCodes are the modifications we can use for splitting packets
    splitCodes = {}
    IPsplitCodes = ['IPs','IPr']
    splitCodes['tcp'] = IPsplitCodes + ['TCPs','TCPr']
    splitCodes['udp'] = IPsplitCodes + ['UDPr']

    # All the configurations used
    configs = Configs()
    configs = setUpConfig(configs)

    if args == []:
        configs.read_args(sys.argv)
    else:
        configs.read_args(args)

    configs.check_for(['pcap_folder', 'num_packets'])

    #The following does a DNS lookup and resolves server's IP address
    try:
        configs.get('serverInstanceIP')
    except KeyError:
        configs.check_for(['serverInstance'])
        configs.set('serverInstanceIP', Instance().getIP(configs.get('serverInstance')))

    PcapDirectory = configs.get('pcap_folder')

    if not PcapDirectory.endswith('/'):
        PcapDirectory = PcapDirectory + '/'

    numPackets = configs.get('num_packets')
    client_ip_file = os.path.abspath(PcapDirectory + '/client_ip.txt')

    configs.set('pcaps',PcapDirectory,)

    with open(client_ip_file,'r') as c:
        client_ip = c.readline().split('\n')[0]

    permaData = PermaData()
    permaData.updateHistoryCount()
    analyzerI = AnalyzerI(configs.get('serverInstanceIP'), configs.get('analyzerPort'))

    # STEP 1
    # Check whether there is differentiation
    changeMeta, csp, Protocol, replayName, clientQ, serverQ = GetMeta(PcapDirectory, numPackets, client_ip)
    PRINT_ACTION('META DATA for The packets that we need to change' + str(changeMeta), 0)
    # Replaycounter records how many replays we ran for this analysis
    global Replaycounter
    # No modification, get original Classification
    nomodify = pickle.dumps(('Client', -1, None, None))
    PRINT_ACTION('Start to replay Original trace',0)
    Classi_Origin = Replay(PcapDirectory, nomodify, analyzerI)

    # Load the randomized trace and perform a replay to check whether DPI based classification
    PRINT_ACTION('Start to replay Randomized trace',0)
    Classi_Random = Replay(PcapDirectory[:-1] + 'Random/', nomodify, analyzerI)

    if Classi_Origin == Classi_Random:
        PRINT_ACTION('NO DPI based differentiation detected. Both original trace and randomized trace are classified the same',0)
        sys.exit()

    # STEP 2, Reverse Engineer the classifier Rule
    PRINT_ACTION('Start reverse engineering the classification contents',0)
    Client = FullAnalysis(PcapDirectory, changeMeta, Classi_Origin, 'Client', analyzerI)
    # This is for testing only
    # Client = {0:['DPI based differentiation, matching regions:', [[0,1,2,3],[98,99,100,101,102,103,104]]]}
    # Server side analysis is not needed for liberate
    # Now we have the client side matching content used by the classifier
    PRINT_ACTION(' Client analysis' + str(Client) + '\r\n Number of Tests:' + str(Replaycounter),0)
    # If no Client Side matching content can be found, abandon, since we can not evade classification then
    DPI = False
    for analysis in Client:
        if Client[analysis][0] == 'DPI based differentiation, matching regions:':
            DPI = True

    if DPI == False:
        print '\r\n No DPI based differentiation has been found within the first ',numPackets, ' packets being tested, exiting'
        sys.exit()

    # print 'Server analysis',Server, 'Number of Tests:', Replaycounter
    # If no Client Side matching content can be found, abandon, since we can not evade classification then
    DPI = False
    for analysis in Client:
        # If any of the client packets has matching field, we can run liberate
        if Client[analysis][0] == 'DPI based differentiation, matching regions:':
            DPI = True

    if DPI == False:
        print Client
        print '\r\n No DPI based differentiation has been found within the first ',numPackets, ' packets being tested, exiting'
        sys.exit()

    # client port is used to determine whether it is HTTP traffic,
    clientport = csp.split('.')[-1]
    # Liberate proxy takes cKeywords as a parameter
    cKeywords = ExtractKeywordClient(clientport, clientQ, Client)
    # sKeywords = ExtractKeywordServer(clientport, serverQ, Protocol, Server)
    print '\n\t Matching Keywords', cKeywords


    # STEP 3, Reverse Engineer the classifier Rule

    # Prepending test, check whether the position of the matching packets matters
    PreNum, PreLen = PrependAnalysis(PcapDirectory, Classi_Origin, 'Client', Protocol, AnalyzerI)
    # PreNum = 1
    # PreLen = 1000


    # GetTTL will probe the location of the classifier
    ProbTTL = GetTTL(PcapDirectory, Classi_Origin, cKeywords, Protocol, PreNum, PreLen, AnalyzerI)
    # ProbTTL = 1

    if ProbTTL == None:
        print 'We failed to locate the classifer, TTL limited techniques can not be used'
        IPinjectionCodes.remove('IPi1')

    # print '\n\t The probed TTL: ',ProbTTL
    # Keywords, PreNum, PreLen , ProbTTL are then used for the liberate proxy, we record those data into Mached.txt

    # Test evading methods iteratively
    EffectiveMethods = []

    # PreNum = 0, it means prepending can not change the classification, we will not try injection in this case
    if PreNum != 0:
        print '\n\t Classification changed after prepending: ', PreNum, ' Packets with length ',PreLen
    #     # We then run the proxy
    #     # This is for inert injection, the ModiNum and ModiSize are given by prepending tests
        for ChangeCode in injectionCodes[Protocol]:
            p = LiberateProxy.LiberateProxy(cKeywords, ChangeCode, Protocol, PreLen, PreNum, ProbTTL)
            EClass = Replay(PcapDirectory, nomodify, AnalyzerI, p)
            if EClass != Classi_Origin:
                method = (ChangeCode, PreLen, PreNum, ProbTTL)
                EffectiveMethods.append(method)
    #
    # Spliting/reordering techniques
    # For splitting, the ModiNum is the number of fragments/segments
    #
    # Split each matching packet into up to PreNum + 1 pieces, since the classifier checks at most PreNum packets

    SplitNum = max(5, PreNum + 1)
    #
    for ChangeCode in splitCodes[Protocol]:
        for ModiNum in range(2, SplitNum):
            print '\n\t Spliting every matching packet into ',ModiNum,' ones'
            print '\n\t Starting Liberate Proxy:',cKeywords, ChangeCode, Protocol, PreLen, ModiNum, ProbTTL
            p = LiberateProxy.LiberateProxy(ChangeCode, Protocol, PreLen, ModiNum, ProbTTL)
            EClass = Replay(PcapDirectory, nomodify, AnalyzerI, p)
            if EClass != Classi_Origin:
                method = (ChangeCode, ModiNum)
                EffectiveMethods.append(method)
    #
    # Flushing techniques, pause for 10s up to 240s
    # IPfa, TCPfa and IPfb, TCPfb
    # Flushing after or before the matching packets
    for FlushTiming in ['a','b']:
        for PauseT in [10, 20, 40, 60, 120, 240]:
            p = LiberateProxy.LiberateProxy(cKeywords, 'IPf'+FlushTiming, Protocol, PreLen, PreNum, ProbTTL, PauseT)
            EClass = Replay(PcapDirectory, nomodify, AnalyzerI, p)
            if EClass != Classi_Origin:
                method = pickle.dumps(('IPf'+FlushTiming, PauseT))
                EffectiveMethods.append(method)
            # We try RST flushing if TCP traffic and IPi1 works, we will inject TTL-limited RST packet
            if (Protocol == 'tcp') and ('IPi1' in EffectiveMethods):
                p = LiberateProxy.LiberateProxy(cKeywords, 'TCPf'+FlushTiming, Protocol, PreLen, PreNum, ProbTTL, PauseT)
                EClass = Replay(PcapDirectory, nomodify, AnalyzerI, p)
                if EClass != Classi_Origin:
                    EffectiveMethods.append(('TCPf'+FlushTiming, ProbTTL))
    #
    print 'All the effective Methods:', EffectiveMethods

    #
    # Step 4, Deploy the first effective method and run liberate proxy with the specification
    # TODO Adding effective Spec, used by this step to load method that are going to deploy
    # Keywords, ChangeCode, Protocol, PreLen, PreNum, ProbTTL, PauseT = pickle.loads(EffectiveMethods[0])
    # p = LiberateProxy.LiberateProxy(Keywords, ChangeCode, Protocol, PreLen, PreNum, ProbTTL, PauseT)
    # # The dport is the destination port in the original pcap, that's where the original server runs
    # dport = csp.split('.')[-1]
    # dport = str(int(dport))
    # subprocess.call('iptables -A OUTPUT -p tcp --dport '+ dport +' -j NFQUEUE --queue-num 1', stdout=subprocess.PIPE , shell=True)
    #
    # try:
    #     p.persistRun()
    # except:
    #     subprocess.call('iptables -D OUTPUT -p tcp --dport '+ dport + '-j NFQUEUE --queue-num 1', stdout=subprocess.PIPE , shell=True)


if __name__=="__main__":
    main(sys.argv)
