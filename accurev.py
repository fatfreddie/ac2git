#!/usr/bin/python3

# ################################################################################################ #
# AccuRev utility script                                                                           #
# Author: Lazar Sumar                                                                              #
# Date:   06/11/2014                                                                               #
#                                                                                                  #
# This script is a library that is intended to expose a Python API to the AccuRev commands and     #
# command result data structures.                                                                  #
# ################################################################################################ #

import sys
import subprocess
import xml.etree.ElementTree as ElementTree
import datetime
import re
import sqlite3

# ################################################################################################ #
# Script Globals                                                                                   #
# ################################################################################################ #


# ################################################################################################ #
# Script Classes                                                                                   #
# ################################################################################################ #
def GetXmlContents(xmlElement):
    if xmlElement is not None:
        text = ''
        if xmlElement.text is not None:
            text = xmlElement.text
        return text + ''.join(ElementTree.tostring(e) for e in xmlElement)
    return None

def IntOrNone(value):
    if value is None:
        return None
    return int(value)

def UTCDateTimeOrNone(value):
    if value is None:
        return None
    if isinstance(value, str) or isinstance(value, int) or isinstance(value, float):
        value = float(value)
        return datetime.datetime.utcfromtimestamp(value)
    if isinstance(value, datetime.datetime):
        return value
    raise Exception("UTCDateTimeOrNone(value={0}) - Invalid conversion!".format(value))

def GetTimestamp(datetimeValue):
    if datetimeValue is None:
        return None
    if type(datetimeValue) is not datetime.datetime:
        raise Exception('Invalid argument. Expected a datetime type.')
    timestamp = (datetimeValue - datetime.datetime(1970, 1, 1)).total_seconds()
    return timestamp

# ################################################################################################ #
# Script Objects                                                                                   #
# ################################################################################################ #
class obj:
    class Bool(object):
        def __init__(self, value):
            if type(value) is bool:
                self.value = value
                self.originalStr = None
            elif type(value) is str:
                self.value = obj.Bool.string2bool(value)
                self.originalStr = value
            else:
                raise Exception("Unknown type to convert to obj.Bool")
    
        def __nonzero__(self):
            return self.value
    
        def __bool__(self):
            return self.value
    
        def __repr__(self):
            if self.originalStr is None:
                return self.toString()
            else:
                return self.originalStr
    
        def toString(self, toTrueFalse=True, toYesNo=False, toUpper=False, toLower=False):
            rv = None
            if toTrueFalse:
                if self.value:
                    rv = "True"
                else:
                    rv = "False"
            else: # toYesNo:
                if self.value:
                    rv = "Yes"
                else:
                    rv = "No"
            if toLower:
                rv = rv.lower()
            elif toUpper:
                rv = rv.upper()
            
            return rv
            
        @staticmethod
        def string2bool(string):
            rv = None
            string = string.lower()
    
            if string == "yes" or string == "true":
                rv = True
            elif string == "no" or string == "false":
                rv = False
            else:
                raise Exception("Bool value invalid")
    
            return rv
    
        @classmethod
        def fromstring(cls, string):
            if string is not None:
                rv = obj.Bool.string2bool(string)
                return cls(rv)
            return None
    
    class TimeSpec(object):
        timeSpecRe = None
        timeSpecPartRe = None

        def __init__(self, start, end=None, limit=None):
            self.start = start
            self.end   = end
            self.limit = limit

        def __repr__(self):
            rv = repr(self.start)
            if self.end is not None:
                rv += '-{0}'.format(repr(self.end))
            if self.limit is not None:
                rv += '.{0}'.format(repr(self.limit))
            return rv

        @staticmethod
        def is_keyword(obj):
            if isinstance(obj, str):
                try:
                    obj = int(obj)
                except:
                    pass
            if isinstance(obj, int):
                return False
            elif obj in [ 'highest', 'now' ]:
                return True
            else:
                return None

        @staticmethod
        def compare_transaction_specs(lhs, rhs):
            # Force them to be ints if they can be.
            try:
                lhs = int(lhs)
            except:
                pass
            try:
                rhs = int(rhs)
            except:
                pass

            # highest > now > any transaction number
            if lhs == rhs:
                return 0
            elif lhs == 'highest':
                return 1
            elif rhs == 'highest':
                return -1
            elif lhs == 'now':
                return 1
            elif rhs == 'now':
                return -1
            elif lhs > rhs:
                return 1
            elif lhs < rhs:
                return -1
            elif lhs is None or rhs is None:
                raise Exception('Can\'t compare to None')
            else:
                raise Exception('How did you get here?')

        def is_asc(self):
            try:
                return obj.TimeSpec.compare_transaction_specs(self.start, self.end) < 0
            except:
                return False

        def is_desc(self):
            try:
                return obj.TimeSpec.compare_transaction_specs(self.start, self.end) > 0
            except:
                return False

        def reversed(self):
            return obj.TimeSpec.reverse(self)

        def is_cacheable(self):
            cacheable = self.start is not None and obj.TimeSpec.is_keyword(self.start) == False
            cacheable = cacheable and (self.end is not None and obj.TimeSpec.is_keyword(self.end) == False)

            return cacheable

        @classmethod
        def reverse(cls, timespec):
            rv = None
            if isinstance(timespec, cls):
                rv = cls(start=timespec.end, end=timespec.start, limit=timespec.limit)
            return rv
        
        @staticmethod
        def parse_simple(timespec):
            rv = None
            if timespec is not None:
                if isinstance(timespec, str):
                    if obj.TimeSpec.timeSpecPartRe is None:
                        obj.TimeSpec.timeSpecPartRe = re.compile(r'^ *(?:(?P<transaction>\d+)|(?P<keyword>now|highest)|(?P<datetime>(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2}) +(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}))) *$')
                    
                    timeSpecPartMatch = obj.TimeSpec.timeSpecPartRe.search(timespec)
                    if timeSpecPartMatch is not None:
                        timeSpecPartDict = timeSpecPartMatch.groupdict()
                        if 'keyword' in timeSpecPartDict and timeSpecPartDict['keyword'] is not None:
                            rv = timeSpecPartDict['keyword']
                        elif 'transaction' in timeSpecPartDict and timeSpecPartDict['transaction'] is not None:
                            rv = int(timeSpecPartDict['transaction'])
                        elif 'datetime' in timeSpecPartDict and timeSpecPartDict['datetime'] is not None:
                            rv = datetime.datetime(year=int(timeSpecPartDict['year']), month=int(timeSpecPartDict['month']), day=int(timeSpecPartDict['day']), hour=int(timeSpecPartDict['hour']), minute=int(timeSpecPartDict['minute']), second=int(timeSpecPartDict['second']))
                elif isinstance(timespec, datetime.datetime):
                    rv = timespec
                elif isinstance(timespec, int):
                    rv = timespec
                else:
                    raise Exception("Unsupported type ({t}) of timespec ({ts}) part!".format(t=type(timespec), ts=str(timespec)))
            return rv

        @classmethod
        def fromstring(cls, string):
            if string is not None:
                if isinstance(string, int):
                    return cls(start=string)
                elif isinstance(string, datetime.datetime):
                    return cls(start=string)
                elif isinstance(string, str):
                    if obj.TimeSpec.timeSpecRe is None:
                        obj.TimeSpec.timeSpecRe = re.compile(r'^(?P<start>.*?) *(?:- *(?P<end>.*?))?(?:\.(?P<limit>\d+))?$')
                    timeSpecMatch = obj.TimeSpec.timeSpecRe.search(string)
                    
                    if timeSpecMatch is not None:
                        timeSpecDict = timeSpecMatch.groupdict()

                        start = end = limit = None
                        if 'start' in timeSpecDict:
                            start = obj.TimeSpec.parse_simple(timeSpecDict['start'])
                        if 'end' in timeSpecDict:
                            end = obj.TimeSpec.parse_simple(timeSpecDict['end'])
                        if 'limit' in timeSpecDict:
                            limit = timeSpecDict['limit']
                        
                        return cls(start=start, end=end, limit=IntOrNone(limit))
                else:
                    raise Exception("Unsupported type ({t}) of string ({s}) that was presented as a timespec.".format(t=type(string), s=str(string)))

            return None

    class Login(object):
        def __init__(self, errorMessage):
            self.errorMessage = errorMessage

        def __repr__(self):
            if self.errorMessage is None or len(self.errorMessage) == 0:
                return "Login success"
            else:
                return self.errorMessage

        def __nonzero__(self):
            return (self.errorMessage is None or len(self.errorMessage) == 0)
    
        def __bool__(self):
            return self.__nonzero__()
    
    class Workspace(object):
        def __init__(self, storage, host, targetTransaction, fileModTime, EOL, Type):
            self.storage           = storage
            self.host              = host
            self.targetTransaction = IntOrNone(targetTransaction)
            self.fileModTime       = UTCDateTimeOrNone(fileModTime)
            self.EOL               = EOL
            self.Type              = Type
            
        def __repr__(self):
            str = "Workspace(storage=" + repr(self.storage)
            str += ", host="               + repr(self.host)
            str += ", targetTransaction="  + repr(self.targetTransaction)
            str += ", fileModTime="        + repr(self.fileModTime)
            str += ", EOL="                + repr(self.EOL)
            str += ", Type="               + repr(self.Type)
            str += ")"
            
            return str
        
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'wspace':
                storage                = xmlElement.attrib.get('Storage')
                host                   = xmlElement.attrib.get('Host')
                targetTransaction      = xmlElement.attrib.get('Target_trans')
                fileModTime            = xmlElement.attrib.get('fileModTime')
                EOL                    = xmlElement.attrib.get('EOL')
                Type                   = xmlElement.attrib.get('Type')
                
                return cls(storage, host, targetTransaction, fileModTime, EOL, Type)
            
            return None
        
    class Stream(object):
        def __init__(self, name, streamNumber, depotName, Type, basis=None, basisStreamNumber=None, time=None, prevTime=None, prevBasis=None, prevBasisStreamNumber=None, prevName=None, workspace=None, startTime=None, isDynamic=None, hasDefaultGroup=None):
            self.name                  = name
            self.streamNumber          = IntOrNone(streamNumber)
            self.depotName             = depotName
            self.Type                  = Type
            self.basis                 = basis
            self.basisStreamNumber     = IntOrNone(basisStreamNumber)
            self.time                  = UTCDateTimeOrNone(time)           # Represents the timelock
            self.prevTime              = UTCDateTimeOrNone(prevTime)
            self.prevBasis             = prevBasis
            self.prevBasisStreamNumber = IntOrNone(prevBasisStreamNumber)
            self.prevName              = prevName
            self.workspace             = workspace
            self.startTime             = UTCDateTimeOrNone(startTime)      # The time at which the last mkstream or chstream transaction was recorded for this stream
            self.isDynamic             = obj.Bool.fromstring(isDynamic)
            self.hasDefaultGroup       = obj.Bool.fromstring(hasDefaultGroup)
    
        def __repr__(self):
            str = "Stream(name="              + repr(self.name)
            str += ", streamNumber="          + repr(self.streamNumber)
            str += ", depotName="             + repr(self.depotName)
            str += ", Type="                  + repr(self.Type)
            str += ", basis="                 + repr(self.basis)
            str += ", basisStreamNumber="     + repr(self.basisStreamNumber)
            str += ", time="                  + repr(self.time)
            str += ", prevTime="              + repr(self.prevTime)
            str += ", prevBasis="             + repr(self.prevBasis)
            str += ", prevBasisStreamNumber=" + repr(self.prevBasisStreamNumber)
            str += ", prevName="              + repr(self.prevName)
            str += ", workspace="             + repr(self.workspace)
            str += ", startTime="             + repr(self.startTime)
            str += ", isDynamic="             + repr(self.isDynamic)
            str += ", hasDefaultGroup="       + repr(self.hasDefaultGroup)
            str += ")"
            
            return str
        
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'stream':
                name                      = xmlElement.attrib.get('name')
                streamNumber              = xmlElement.attrib.get('streamNumber')
                if streamNumber is None:
                    streamNumber          = xmlElement.attrib.get('id')
                depotName                 = xmlElement.attrib.get('depotName')
                Type                      = xmlElement.attrib.get('type')
                basis                     = xmlElement.attrib.get('basis')
                basisStreamNumber         = xmlElement.attrib.get('basisStreamNumber')
                time                      = xmlElement.attrib.get('time')
                prevTime                  = xmlElement.attrib.get('prevTime')
                prevBasis                 = xmlElement.attrib.get('prevBasis')
                prevBasisStreamNumber     = xmlElement.attrib.get('prevBasisStreamNumber')
                prevName                  = xmlElement.attrib.get('prevName')
                startTime                 = xmlElement.attrib.get('startTime')
                isDynamic                 = xmlElement.attrib.get('isDynamic')
                hasDefaultGroup           = xmlElement.attrib.get('hasDefaultGroup')
                
                wspaceElement = xmlElement.find('wspace')
                workspace = obj.Workspace.fromxmlelement(wspaceElement)
                
                return cls(name=name, streamNumber=streamNumber, depotName=depotName, Type=Type, basis=basis, basisStreamNumber=basisStreamNumber, time=time, prevTime=prevTime, prevBasis=prevBasis, prevBasisStreamNumber=prevBasisStreamNumber, prevName=prevName, workspace=workspace, startTime=startTime, isDynamic=isDynamic, hasDefaultGroup=hasDefaultGroup)
            
            return None
        
    class Move(object):
        def __init__(self, dest = None, source = None):
            self.dest   = dest
            self.source = source
            
        def __repr__(self):
            str = "Move(dest=" + repr(self.dest)
            str += ", source="        + repr(self.source)
            str += ")"
            
            return str
        
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'move':
                dest                      = xmlElement.attrib.get('dest')
                source                    = xmlElement.attrib.get('source')
                
                return cls(dest, source)
            
            return None
        
    class Version(object):
        def __init__(self, stream=None, version=None):
            self.stream  = stream
            self.version = version
        
        def __repr__(self):
            return '{0}/{1}'.format(self.stream, self.version)
            
        @classmethod
        def fromstring(cls, versionString):
            if versionString is not None:
                versionParts = versionString.replace('\\', '/').split('/')
                if len(versionParts) == 2:
                    stream  = versionParts[0]
                    if re.match('^[0-9]+$', stream):
                        stream = int(stream)
                    version = int(versionParts[1])
                    
                    return cls(stream, version)
            
            return None
        
    class Transaction(object):
        class Version(object):
            class RevertSegment(object):
                def __init__(self, headStream=None, headStreamName=None, headVersion=None, basisStream=None, basisStreamName=None, basisVersion=None, isTipVersion=None):
                    self.headStream      = IntOrNone(headStream)
                    self.headStreamName  = headStreamName
                    self.headVersion     = IntOrNone(headVersion)
                    self.basisStream     = IntOrNone(basisStream)
                    self.basisStreamName = basisStreamName
                    self.basisVersion    = IntOrNone(basisVersion)
                    self.isTipVersion    = obj.Bool.fromstring(isTipVersion)

                def __repr__(self):
                    str = "obj.Transaction.Version.RevertSegment("
                    str += "headStream=" + repr(self.headStream)
                    str += ", headStreamName=" + repr(self.headStreamName)
                    str += ", headVersion=" + repr(self.headVersion)
                    str += ", basisStream=" + repr(self.basisStream)
                    str += ", basisStreamName=" + repr(self.basisStreamName)
                    str += ", basisVersion=" + repr(self.basisVersion)
                    str += ", isTipVersion=" + repr(self.isTipVersion)
                    return str

                @classmethod
                def fromxmlelement(cls, xmlElement):
                    if xmlElement is not None and xmlElement.tag == 'segment':
                        headStream      = xmlElement.attrib.get('head_stream')
                        headStreamName  = xmlElement.attrib.get('head_stream_name')
                        headVersion     = xmlElement.attrib.get('head_version')
                        basisStream     = xmlElement.attrib.get('basis_stream')
                        basisStreamName = xmlElement.attrib.get('basis_stream_name')
                        basisVersion    = xmlElement.attrib.get('basis_version')
                        isTipVersion    = xmlElement.attrib.get('is_tip_version')
                        return cls(headStream=headStream, headStreamName=headStreamName, headVersion=headVersion, basisStream=basisStream, basisStreamName=basisStreamName, basisVersion=basisVersion, isTipVersion=isTipVersion)

                    return None

            def __init__(self, path, eid, virtual, real, virtualNamedVersion, realNamedVersion, ancestor=None, ancestorNamedVersion=None, mergedAgainst=None, mergedAgainstNamedVersion=None, elemType=None, dir=None, mtime=None, checksum=None, size=None, revertSegments=None):
                self.path                      = path
                self.eid                       = IntOrNone(eid)
                self.virtual                   = obj.Version.fromstring(virtual)
                self.real                      = obj.Version.fromstring(real)
                self.virtualNamedVersion       = obj.Version.fromstring(virtualNamedVersion)
                self.realNamedVersion          = obj.Version.fromstring(realNamedVersion)
                self.ancestor                  = obj.Version.fromstring(ancestor)
                self.ancestorNamedVersion      = obj.Version.fromstring(ancestorNamedVersion)
                self.mergedAgainst             = obj.Version.fromstring(mergedAgainst)
                self.mergedAgainstNamedVersion = obj.Version.fromstring(mergedAgainstNamedVersion)
                self.elemType                  = elemType
                self.dir                       = obj.Bool.fromstring(dir)
                self.mtime                     = UTCDateTimeOrNone(mtime)
                self.checksum                  = checksum
                self.size                      = size
                self.revertSegments            = revertSegments # Either None or a list of revert segments
        
            def __repr__(self):
                str = "Transaction.Version(path="    + repr(self.path)
                str += ", eid="                 + repr(self.eid)
                str += ", virtual="             + repr(self.virtual)
                str += ", real="                + repr(self.real)
                str += ", virtualNamedVersion=" + repr(self.virtualNamedVersion)
                str += ", realNamedVersion="    + repr(self.realNamedVersion)
                if self.ancestor is not None or self.ancestorNamedVersion is not None:
                    str += ", ancestor="    + repr(self.ancestor)
                    str += ", ancestorNamedVersion="    + repr(self.ancestorNamedVersion)
                if self.mergedAgainst is not None or self.mergedAgainstNamedVersion is not None:
                    str += ", mergedAgainst="    + repr(self.mergedAgainst)
                    str += ", mergedAgainstNamedVersion="    + repr(self.mergedAgainstNamedVersion)
                str += ", elemType="            + repr(self.elemType)
                str += ", dir="                 + repr(self.dir)
                if self.mtime is not None:
                    str += ", mtime="           + repr(self.mtime)
                if self.checksum is not None:
                    str += ", cksum="           + repr(self.checksum)
                if self.size is not None:
                    str += ", size="            + repr(self.size)
                if self.revertSegments is not None:
                    str += ", revertSegments="  + repr(self.revertSegments)
                str += ")"
                
                return str
            
            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == 'version':
                    path                      = xmlElement.attrib.get('path')
                    eid                       = xmlElement.attrib.get('eid')
                    virtual                   = xmlElement.attrib.get('virtual')
                    real                      = xmlElement.attrib.get('real')
                    virtualNamedVersion       = xmlElement.attrib.get('virtualNamedVersion')
                    realNamedVersion          = xmlElement.attrib.get('realNamedVersion')
                    ancestor                  = xmlElement.attrib.get('ancestor')
                    ancestorNamedVersion      = xmlElement.attrib.get('ancestorNamedVersion')
                    mergedAgainst             = xmlElement.attrib.get('merged_against')
                    mergedAgainstNamedVersion = xmlElement.attrib.get('mergedAgainstNamedVersion')
                    elemType                  = xmlElement.attrib.get('elem_type')
                    dir                       = xmlElement.attrib.get('dir')
                    mtime                     = xmlElement.attrib.get('mtime')
                    cksum                     = xmlElement.attrib.get('cksum')
                    sz                        = xmlElement.attrib.get('sz')
                    
                    revertSegments = None
                    revertSegmentsElem = xmlElement.find('revertSegments')
                    if revertSegmentsElem is not None:
                        revertSegments = []
                        segmentsElemList = revertSegmentsElem.findall('segment')
                        for segmentElem in segmentsElemList:
                            revertSegments.append(obj.Transaction.Version.RevertSegment.fromxmlelement(segmentElem))

                    return cls(path, eid, virtual, real, virtualNamedVersion, realNamedVersion, ancestor, ancestorNamedVersion, mergedAgainst, mergedAgainstNamedVersion, elemType, dir, mtime, cksum, sz, revertSegments)

                
                return None
            
        def __init__(self, id, Type, time, user, comment, streamName=None, streamNumber=None, fromStreamName=None, fromStreamNumber=None, versions = [], moves = [], stream = None):
            self.id               = IntOrNone(id)
            self.Type             = Type
            self.time             = UTCDateTimeOrNone(time)
            self.user             = user
            self.streamName       = streamName
            self.streamNumber     = IntOrNone(streamNumber)
            self.fromStreamName   = fromStreamName
            self.fromStreamNumber = IntOrNone(fromStreamNumber)
            self.comment          = comment
            self.versions         = versions
            self.moves            = moves
            self.stream           = stream
            
        def __repr__(self):
            str = "Transaction(id="          + repr(self.id)
            str += ", Type="                 + repr(self.Type)
            str += ", time="                 + repr(self.time)
            str += ", user="                 + repr(self.user)
            if self.streamName is not None:
                str += ", streamName="       + repr(self.streamName)
            if self.streamNumber is not None:
                str += ", streamNumber="     + repr(self.streamNumber)
            if self.fromStreamName is not None:
                str += ", fromStreamName="   + repr(self.fromStreamName)
            if self.fromStreamNumber is not None:
                str += ", fromStreamNumber=" + repr(self.fromStreamNumber)
            str += ", comment="              + repr(self.comment)
            if len(self.versions) > 0:
                str += ", versions="         + repr(self.versions)
            if len(self.moves) > 0:
                str += ", moves="            + repr(self.moves)
            if self.stream is not None:
                str += ", stream="           + repr(self.stream)
            str += ")"
            
            return str

        # Extension method which returns the name or number of the stream
        # which is affected by this transaction (the stream on which the
        # transaction was performed). i.e. A promote to a stream called
        # Stream1 whose id is 1734 would return ("Stream1", 1734).
        def affectedStream(self):
            streamName   = self.streamName
            streamNumber = self.streamNumber
            if streamName is None and streamNumber is None:
                if self.versions is not None and len(self.versions) > 0:
                    version = self.versions[0]
                    if version.virtualNamedVersion is not None:
                        streamName   = version.virtualNamedVersion.stream
                    if version.virtual is not None:
                        streamNumber = int(version.virtual.stream)
                elif self.stream is not None:
                    streamName   = self.stream.name
                    streamNumber = self.stream.streamNumber

            return (streamName, streamNumber)
        
        def toStream(self):
            return self.affectedStream()
        
        def fromStream(self):
            fromStreamName   = self.fromStreamName
            fromStreamNumber = self.fromStreamNumber
            return (fromStreamName, fromStreamNumber)

        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'transaction':
                id               = xmlElement.attrib.get('id')
                Type             = xmlElement.attrib.get('type')
                time             = xmlElement.attrib.get('time')
                user             = xmlElement.attrib.get('user')
                streamName       = xmlElement.attrib.get('streamName')
                streamNumber     = xmlElement.attrib.get('streamNumber')
                fromStreamName   = xmlElement.attrib.get('fromStreamName')
                fromStreamNumber = xmlElement.attrib.get('fromStreamNumber')
                comment          = GetXmlContents(xmlElement.find('comment'))
    
                versions = []
                for versionElement in xmlElement.findall('version'):
                    versions.append(obj.Transaction.Version.fromxmlelement(versionElement))
    
                moves = []
                for moveElement in xmlElement.findall('move'):
                    moves.append(obj.Move.fromxmlelement(moveElement))
    
                streamElement = xmlElement.find('stream')
                stream = obj.Stream.fromxmlelement(streamElement)
    
                return cls(id=id, Type=Type, time=time, user=user, comment=comment, streamName=streamName, streamNumber=streamNumber, fromStreamName=fromStreamName, fromStreamNumber=fromStreamNumber, versions=versions, moves=moves, stream=stream)
    
            return None
    
    class History(object):
        def __init__(self, taskId = None, transactions = [], streams = []):
            self.taskId       = IntOrNone(taskId)
            self.transactions = transactions
            self.streams      = streams
    
        def __repr__(self):
            str = "History(taskId="  + repr(self.taskId)
            str += ", transactions=" + repr(self.transactions)
            str += ", streams="      + repr(self.streams)
            str += ")"
    
            return str
    
        @classmethod
        def fromxmlstring(cls, xmlText):
            try:
                # Load the XML
                xmlRoot = ElementTree.fromstring(xmlText)
                #xpathPredicate = ".//AcResponse[@Command='hist']"
            except ElementTree.ParseError:
                return None
    
            if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "hist":
                # Build the class
                taskId = xmlRoot.attrib.get('TaskId')
    
                transactions = []
                for transactionElement in xmlRoot.findall('transaction'):
                    transactions.append(obj.Transaction.fromxmlelement(transactionElement))
    
                streams = []
                streamsElement = xmlRoot.find('streams')
                if streamsElement is not None:
                    for streamElement in streamsElement:
                        streams.append(obj.Stream.fromxmlelement(streamElement))
    
    
                return cls(taskId=taskId, transactions=transactions, streams=streams)
            else:
                # Invalid XML for an AccuRev hist command response.
                return None

        # Returns a list of (streamName, streamNumber) tuples that directly correspond to the
        # destination streams of the transactions. i.e. If there are 5 transactions there would
        # be 5 tuples (even if they are all for the same stream). The 4th tuple is the destination
        # stream for the 4th transaction.
        def toStreams(self):
            toStreams = []
            toStreamName, toStreamNumber = None, None
            if self.transactions is None:
                # Can't workout the source stream for a None transaction.
                return None, None
            elif self.streams is not None and len(self.streams) == 1:
                for tr in self.transactions:
                    toStreams.append( (self.streams[0].name, self.streams[0].streamNumber) )
            else:
                for tr in self.transactions:
                    toStreamName, toStreamNumber = tr.toStream()
                    toStreams.append( (toStreamName, toStreamNumber) )

            return toStreams
        
        def toStream(self):
            if self.streams is not None and len(self.streams) == 1:
                return self.streams[0].name, self.streams[0].streamNumber
            else:
                toStreams = self.toStreams()
                if len(toStreams) > 1:
                    raise Exception("Error! Could not determine which of the many destination streams was the destination stream!")
                return toStreams[0]

        # Pre accurev 6.1 determining the from stream was difficult since the fromStreamName attribute of the transaction
        # was missing. However, if you only queried a single transaction (i.e. `accurev hist -p Depot -t 71 -fex`) then
        # there would be one transaction but two streams listed. From this we can work out which stream things were promoted
        # to and infer that the other stream that is included is the stream from which the promote came from.
        # Hence, since both the transactions and streams are required to do this, the History object should do it for this one
        # very specific case.
        def fromStream(self):
            if self.transactions is None:
                # Can't workout the source stream for a None transaction.
                return None, None
            elif len(self.transactions) != 1:
                # Can't work out the source stream for multiple transactions.
                return None, None
            
            fromStreamName, fromStreamNumber = self.transactions[0].fromStream()
            if fromStreamName is None:
                toStreamName, toStreamNumber = self.toStream()
                if toStreamName is not None and toStreamNumber is not None and self.streams is not None and len(self.streams) == 2:
                    fromStream = None
                    if self.streams[0].streamNumber == toStreamNumber:
                        fromStream = self.streams[1]
                    elif self.streams[1].streamNumber == toStreamNumber:
                        fromStream = self.streams[0]
                    else:
                        raise Exception("Error! Failed to match destination stream {s} (id {n}) to either of the two affected streams {s1} (id {s1num}) and {s2} (id {s2num}).".format(s=toStreamName, n=toStreamNumber, s1=self.streams[0].name, s1num=self.streams[0].streamNumber, s2=self.streams[1].name, s2num=self.streams[1].streamNumber))
                    
                    fromStreamName, fromStreamNumber = fromStream.name, fromStream.streamNumber
                else:
                    # Error! Could not determine the source stream.
                    return None, None
            
            return (fromStreamName, fromStreamNumber)
    
    class Stat(object):
        class Element(object):
            def __init__(self, location=None, isDir=False, isExecutable=False, id=None, elemType=None, size=None, modTime=None, hierType=None, virtualVersion=None, namedVersion=None, realVersion=None, status=None):
                self.location       = location
                self.isDir          = obj.Bool.fromstring(isDir)
                self.isExecutable   = obj.Bool.fromstring(isExecutable)
                self.id             = IntOrNone(id)
                self.elemType       = elemType
                self.size           = IntOrNone(size)
                self.modTime        = UTCDateTimeOrNone(modTime)
                self.hierType       = hierType
                self.virtualVersion = obj.Version.fromstring(virtualVersion)
                self.namedVersion   = obj.Version.fromstring(namedVersion)
                self.realVersion    = obj.Version.fromstring(realVersion)
                self.status         = status
                self.statusList     = self._ParseStatusIntoList(status)
        
            def __repr__(self):
                str = "Stat.Element(location=" + repr(self.location)
                str += ", isDir="             + repr(self.isDir)
                str += ", isExecutable="      + repr(self.isExecutable)
                str += ", id="                + repr(self.id)
                str += ", elemType="          + repr(self.elemType)
                str += ", size="              + repr(self.size)
                str += ", modTime="           + repr(self.modTime)
                str += ", hierType="          + repr(self.hierType)
                str += ", virtualVersion="    + repr(self.virtualVersion)
                str += ", namedVersion="      + repr(self.namedVersion)
                str += ", realVersion="       + repr(self.realVersion)
                str += ", status="            + repr(self.status)
                str += ", statusList="        + repr(self.statusList)
                str += ")"
        
                return str
        
            def _ParseStatusIntoList(self, status):
                if status is not None:
                    statusList = []
                    statusItem = None
                    # The following regex takes a parenthesised text like (member)(defunct) and matches it
                    # putting the first matched parenthesised expression (of which there could be more than one)
                    # into the capture group one.
                    # Regex: Match open bracket, consume all characters that are NOT a closed bracket, match the
                    #        closed bracket and return the capture group.
                    reStatusToken = re.compile("(\\([^\\)]+\\))")
                    
                    matchObj = reStatusToken.match(status)
                    while matchObj and len(status) > 0:
                        statusItem = matchObj.group(1)
                        statusList.append(statusItem)
                        status = status[len(statusItem):]
                        matchObj = reStatusToken.match(status)
                    
                    if len(status) != 0:
                        sys.stderr.write("Error: invalidly parsed status! Remaining text is \"{0}\"\n".format(status))
                        return None
                    return statusList
                return None
                
            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == "element":
                    location       = xmlElement.attrib.get('location')
                    isDir          = xmlElement.attrib.get('dir')
                    isExecutable   = xmlElement.attrib.get('executable')
                    id             = xmlElement.attrib.get('id')
                    elemType       = xmlElement.attrib.get('elemType')
                    size           = xmlElement.attrib.get('size')
                    modTime        = xmlElement.attrib.get('modTime')
                    hierType       = xmlElement.attrib.get('hierType')
                    virtualVersion = xmlElement.attrib.get('Virtual')
                    namedVersion   = xmlElement.attrib.get('namedVersion')
                    realVersion    = xmlElement.attrib.get('Real')
                    status         = xmlElement.attrib.get('status')
        
                    return cls(location=location, isDir=isDir, isExecutable=isExecutable, id=id, elemType=elemType, size=size, modTime=modTime, hierType=hierType, virtualVersion=virtualVersion, namedVersion=namedVersion, realVersion=realVersion, status=status)
                else:
                    return None
    
        def __init__(self, taskId=None, directory=None, elements=[]):
            self.taskId    = IntOrNone(taskId)
            self.directory = directory
            self.elements  = elements
    
        def __repr__(self):
            str = "Stat(taskId="  + repr(self.taskId)
            str += ", directory=" + repr(self.directory)
            str += ", elements="  + repr(self.elements)
            str += ")"
    
            return str
    
        @classmethod
        def fromxmlstring(cls, xmlText):
            try:
                xmlRoot = ElementTree.fromstring(xmlText)
            except ElementTree.ParseError:
                return None
    
            if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "stat":
                taskId    = xmlRoot.attrib.get('TaskId')
                directory = xmlRoot.attrib.get('Directory')
    
                elements = []
                for element in xmlRoot.findall('element'):
                    elements.append(obj.Stat.Element.fromxmlelement(element))
    
                return cls(taskId=taskId, directory=directory, elements=elements)
            else:
                return None
    
    class Change(object):
        class Stream(object):
            def __init__(self, name, eid, version, namedVersion, isDir, elemType):
                self.name         = name
                self.eid          = IntOrNone(eid)
                self.version      = obj.Version.fromstring(version)
                self.namedVersion = obj.Version.fromstring(namedVersion)
                self.isDir        = obj.Bool.fromstring(isDir)
                self.elemType     = elemType
            
            def __repr__(self):
                str = "Change.Stream(name=" + repr(self.name)
                str += ", eid="             + repr(self.eid)
                str += ", version="         + repr(self.version)
                str += ", namedVersion="    + repr(self.namedVersion)
                str += ", isDir="           + repr(self.isDir)
                str += ", elemType="        + repr(self.elemType)
                str += ")"
        
                return str
            
            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and re.match('^Stream[12]$', xmlElement.tag) is not None:
                    name         = xmlElement.attrib.get('Name')
                    eid          = xmlElement.attrib.get('eid')
                    version      = xmlElement.attrib.get('Version')
                    namedVersion = xmlElement.attrib.get('NamedVersion')
                    isDir        = xmlElement.attrib.get('IsDir')
                    elemType     = xmlElement.attrib.get('elemType')
                    
                    return cls(name=name, eid=eid, version=version, namedVersion=namedVersion, isDir=isDir, elemType=elemType)
                
                return None
        
        def __init__(self, what, stream1, stream2):
            self.what    = what
            self.stream1 = stream1
            self.stream2 = stream2
        
        def __repr__(self):
            str = "Change(what=" + repr(self.what)
            str += ", stream1="        + repr(self.stream1)
            str += ", stream2="        + repr(self.stream2)
            str += ")"
    
            return str
        
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'Change':
                what = xmlElement.attrib.get('What')
                stream1Elem = xmlElement.find('Stream1')
                stream1 = obj.Change.Stream.fromxmlelement(stream1Elem)
                stream2Elem = xmlElement.find('Stream2')
                stream2 = obj.Change.Stream.fromxmlelement(stream2Elem)
                
                return cls(what=what, stream1=stream1, stream2=stream2)
            
            return None
        
    class Diff(object):
        class Element(object):
            def __init__(self, changes = []):
                self.changes = changes
            
            def __repr__(self):
                str = "Diff.Element(changes=" + repr(self.changes)
                str += ")"
        
                return str
            
            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == 'Element':
                    changes = []
                    for change in xmlElement.findall('Change'):
                        changes.append(obj.Change.fromxmlelement(change))
                    
                    return cls(changes=changes)
                
                return None
            
        def __init__(self, taskId, elements=[]):
            self.taskId    = IntOrNone(taskId)
            self.elements  = elements
        
        def __repr__(self):
            str = "Diff(taskId=" + repr(self.taskId)
            str += ", elements=" + repr(self.elements)
            str += ")"
    
            return str
            
        @classmethod
        def fromxmlstring(cls, xmlText):
            # This parser has been made from an example given by running:
            #   accurev diff -a -i -v Stream -V Stream -t 11-16 -fx
            try:
                xmlRoot = ElementTree.fromstring(xmlText)
            except ElementTree.ParseError:
                return None
    
            if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "diff":
                taskId    = xmlRoot.attrib.get('TaskId')
    
                elements = []
                for element in xmlRoot.findall('Element'):
                    elements.append(obj.Diff.Element.fromxmlelement(element))
    
                return cls(taskId=taskId, elements=elements)
            else:
                return None
        
    class User(object):
        def __init__(self, number = None, name = None, kind = None):
            self.number = IntOrNone(number)
            self.name   = name
            self.kind   = kind
            
        def __repr__(self):
            str = "User(number=" + repr(self.number)
            str += ", name="            + repr(self.name)
            str += ", kind="            + repr(self.kind)
            str += ")"
            
            return str
        
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'Element':
                number = xmlElement.attrib.get('Number')
                name   = xmlElement.attrib.get('Name')
                kind   = xmlElement.attrib.get('Kind')
                
                return cls(number, name, kind)
            
            return None

    class Show(object):
        class Users(object):
            def __init__(self, taskId = None, users = []):
                self.taskId = IntOrNone(taskId)
                self.users  = users
            
            def __repr__(self):
                str = "Show.Users(taskId=" + repr(self.taskId)
                str += ", users="                  + repr(self.users)
                str += ")"
                
                return str
                
            @classmethod
            def fromxmlstring(cls, xmlText):
                try:
                    xmlRoot = ElementTree.fromstring(xmlText)
                except ElementTree.ParseError:
                    return None
    
                if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "show users":
                    taskId = xmlRoot.attrib.get('TaskId')
                    
                    users = []
                    for userElement in xmlRoot.findall('Element'):
                        users.append(obj.User.fromxmlelement(userElement))
                    
                    return cls(taskId=taskId, users=users)
                else:
                    return None
                    
        class Depots(object):
            class Depot(object):
                def __init__(self, number=None, name=None, slice=None, exclusiveLocking=None, case=None, locWidth=None, hidden=None, replStatus=None):
                    self.number           = IntOrNone(number)
                    self.name             = name
                    self.slice            = slice
                    self.exclusiveLocking = exclusiveLocking
                    self.case             = case
                    self.locWidth         = locWidth
                    self.hidden           = obj.Bool.fromstring(hidden)
                    self.replStatus       = replStatus
                    
                def __repr__(self):
                    str = "Show.Depots.Depot(number="        + repr(self.number)
                    str += ", name="             + repr(self.name)
                    str += ", slice="            + repr(self.slice)
                    str += ", exclusiveLocking=" + repr(self.exclusiveLocking)
                    str += ", case="             + repr(self.case)
                    str += ", locWidth="         + repr(self.locWidth)
                    if self.hidden is not None:
                        str += ", hidden="       + repr(self.hidden)
                    str += ", replStatus="       + repr(self.replStatus)
                    str += ")"
                    
                    return str
                
                @classmethod
                def fromxmlelement(cls, xmlElement):
                    if xmlElement is not None and xmlElement.tag == 'Element':
                        number           = xmlElement.attrib.get('Number')
                        name             = xmlElement.attrib.get('Name')
                        slice            = xmlElement.attrib.get('Slice')
                        exclusiveLocking = xmlElement.attrib.get('exclusiveLocking')
                        case             = xmlElement.attrib.get('case')
                        locWidth         = xmlElement.attrib.get('locWidth')
                        hidden           = xmlElement.attrib.get('hidden')
                        replStatus       = xmlElement.attrib.get('ReplStatus')
                        
                        return cls(number, name, slice, exclusiveLocking, case, locWidth, hidden, replStatus)
                    
                    return None
                        
            def __init__(self, taskId = None, depots = []):
                self.taskId = IntOrNone(taskId)
                self.depots = depots
            
            def __repr__(self):
                str = "Show.Depots(taskId=" + repr(self.taskId)
                str += ", depots="         + repr(self.depots)
                str += ")"
                
                return str

            # Gets the depot from the list whose name or number match nameOrNumber.
            def getDepot(self, nameOrNumber):
                # Sanitize the inputs.
                if self.depots is None or len(self.depots) == 0:
                    return None
                elif nameOrNumber is None:
                    return None
                # Prepare state
                name = None
                depotNumber = None
                if isinstance(nameOrNumber, int):
                    depotNumber = nameOrNumber
                else:
                    name = nameOrNumber
                    try:
                        depotNumber = int(nameOrNumber)
                    except:
                        pass
                # Find the matching stream
                for depot in self.depots:
                    if (name is not None and name == depot.name) or (depotNumber is not None and depotNumber == depot.number):
                        return depot
                # Not found
                return None
                
            @classmethod
            def fromxmlstring(cls, xmlText):
                try:
                    xmlRoot = ElementTree.fromstring(xmlText)
                except ElementTree.ParseError:
                    return None
                
                if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "show depots":
                    taskId = xmlRoot.attrib.get('TaskId')
                    
                    depots = []
                    for depotElement in xmlRoot.findall('Element'):
                        depots.append(obj.Show.Depots.Depot.fromxmlelement(depotElement))
                    
                    return cls(taskId=taskId, depots=depots)
                else:
                    return None
                    
        class Streams(object):
            def __init__(self, taskId = None, streams = []):
                self.taskId = IntOrNone(taskId)
                self.streams = streams
            
            def __repr__(self):
                str = "Show.Streams(taskId=" + repr(self.taskId)
                str += ", streams="         + repr(self.streams)
                str += ")"
                
                return str

            # Gets the stream from the list whose name or number match nameOrNumber.
            # Warning: Searching for streams via show.streams(stream="Stream_Name", timeSpec=1234)
            #          will work for the current and all past names of the stream 
            #          if the stream has been renamed. This method will find and
            #          return the stream only if its name matches exactly what it was
            #          called at that point in time (i.e. at transaction 1234).
            # Recommendation: Always use stream number for searches.
            def getStream(self, nameOrNumber):
                # Sanitize the inputs.
                if self.streams is None or len(self.streams) == 0:
                    return None
                elif nameOrNumber is None:
                    return None
                # Prepare state
                name = None
                streamNumber = None
                if isinstance(nameOrNumber, int):
                    streamNumber = nameOrNumber
                else:
                    name = nameOrNumber
                    try:
                        streamNumber = int(nameOrNumber)
                    except:
                        pass
                # Find the matching stream
                for stream in self.streams:
                    if (name is not None and name == stream.name) or (streamNumber is not None and streamNumber == stream.streamNumber):
                        return stream
                # Not found
                return None
                
            @classmethod
            def fromxmlstring(cls, xmlText):
                try:
                    xmlRoot = ElementTree.fromstring(xmlText)
                except ElementTree.ParseError:
                    return None
    
                if xmlRoot is not None and xmlRoot.tag == "streams":
                    taskId = xmlRoot.attrib.get('TaskId')
                    
                    streams = []
                    for streamElement in xmlRoot.findall('stream'):
                        streams.append(obj.Stream.fromxmlelement(streamElement))
                    
                    return cls(taskId=taskId, streams=streams)
                else:
                    return None
    
    class Ancestor(object):
        def __init__(self, location = None, stream = None, version = None, virtualVersion = None):
            self.location       = location
            self.stream         = stream
            self.version        = obj.Version.fromstring(version)
            self.virtualVersion = obj.Version.fromstring(virtualVersion)
        
        def __repr__(self):
            str = "Update(location="   + repr(self.location)
            str += ", stream="         + repr(self.stream)
            str += ", version="        + repr(self.version)
            str += ", virtualVersion=" + repr(self.virtualVersion)
            str += ")"
            
            return str
            
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'element':
                location       = xmlElement.attrib.get('location')
                stream         = xmlElement.attrib.get('stream')
                version        = xmlElement.attrib.get('version')
                virtualVersion = xmlElement.attrib.get('VirtualVersion')
                
                return cls(location, stream, version, virtualVersion)
                
            return None
        
        @classmethod
        def fromxmlstring(cls, xmlString):
            try:
                xmlRoot = ElementTree.fromstring(xmlText)
            except ElementTree.ParseError:
                return None
            
            if xmlRoot is not None and xmlRoot.tag == "acResponse" and xmlRoot.attrib.get("command") == "anc":
                return obj.Ancestor.fromxmlelement(xmlRoot.find('element'))
            return None
    
    class CommandProgress(object):
        def __init__(self, phase = None, increment = None, number = None):
            self.phase     = phase
            self.increment = increment
            self.number    = IntOrNone(number)
        
        def __repr__(self):
            str = "Update(phase=" + repr(self.phase)
            str += ", increment=" + repr(self.increment)
            str += ", number="    + repr(self.number)
            str += ")"
            
            return str
            
        @classmethod
        def fromxmlelement(cls, xmlElement):
            if xmlElement is not None and xmlElement.tag == 'progress':
                phase     = xmlElement.attrib.get('phase')
                increment = xmlElement.attrib.get('increment')
                number    = xmlElement.attrib.get('number')
                
                return cls(phase, increment, number)
                
            return None
    
    class Update(object):
        class Element(object):
            def __init__(self, location = None):
                self.location = location
            
            def __repr__(self):
                str = "Update.Element(location=" + repr(self.location)
                str += ")"
                
                return str
                
            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == 'element':
                    location = xmlElement.attrib.get('location')
                    return cls(location)
                return None
        
        def __init__(self, taskId = None, progressItems = None, messages = None, elements = None):
            self.taskId        = IntOrNone(taskId)
            self.progressItems = streams
            self.messages      = messages
            self.elements      = elements
        
        def __repr__(self):
            str = "Update(taskId="    + repr(self.taskId)
            str += ", progressItems=" + repr(self.progressItems)
            str += ", messages="      + repr(self.messages)
            str += ", elements="      + repr(self.elements)
            str += ")"
            
            return str
            
        @classmethod
        def fromxmlstring(cls, xmlText):
            try:
                xmlRoot = ElementTree.fromstring(xmlText)
            except ElementTree.ParseError:
                return None

            if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "update":
                # Build the class
                taskId = xmlRoot.attrib.get('TaskId')
                
                progressItems = []
                for progressElement in xmlRoot.findall('progress'):
                    progressItems.append(obj.CommandProgress.fromxmlelement(progressElement))
                
                messages = []
                for messageElement in xmlRoot.findall('message'):
                    messages.append(GetXmlContents(messageElement))
                
                elements = []
                for element in xmlRoot.findall('element'):
                    messages.append(obj.Update.Element.fromxmlelement(element))
                
                return cls(taskId=taskId, progressItems=progressItems, messages=messages, elements=elements)
            else:
                return None

    class Pop(object):
        class Message(object):
            def __init__(self, text = None, error = None):
                self.text  = text
                try:
                    self.error = obj.Bool(error)
                except:
                    self.error = None

            def __repr__(self):
                s =  "Pop.Message(text=" + repr(self.text)
                s += ", error="          + repr(self.error)
                s += ")"

                return s

            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == "message":
                    error = xmlElement.attrib.get('error')
                    text  = xmlElement.text

                    return cls(text=text, error=error)
                else:
                    return None

        class Element(object):
            def __init__(self, location = None):
                self.location = location

            def __repr__(self):
                s =  "Pop.Element(location=" + repr(self.location)
                s += ")"

                return s

            @classmethod
            def fromxmlelement(cls, xmlElement):
                if xmlElement is not None and xmlElement.tag == "element":
                    location = xmlElement.attrib.get('location')

                    return cls(location=location)
                else:
                    return None

        def __init__(self, taskId = None, messages = None, elements = None):
            self.taskId   = IntOrNone(taskId)
            self.messages = messages
            self.elements = elements

        def __repr__(self):
            s =  "Pop(taskId=" + repr(self.taskId)
            s += ", messages=" + repr(self.messages)
            s += ", elements=" + repr(self.elements)
            s += ")"

            return s

        def __nonzero__(self):
            return self.__bool__()

        def __bool__(self):
            rv = self.Success()
            if rv is None:
                rv = False
            return rv

        def Success(self):
            if self.messages is not None:
                for message in self.messages:
                    if bool(message.error) == True:
                        return False
                return True
            else:
                return None

        @classmethod
        def fromxmlstring(cls, xmlText):
            try:
                xmlRoot = ElementTree.fromstring(xmlText)
            except ElementTree.ParseError:
                return None

            if xmlRoot is not None and xmlRoot.tag == "AcResponse" and xmlRoot.get("Command") == "pop":
                taskId = xmlRoot.attrib.get('TaskId')

                messages = []
                for messageElement in xmlRoot.findall('message'):
                    messages.append(obj.Pop.Message.fromxmlelement(messageElement))

                elements = []
                for elementElement in xmlRoot.findall('element'):
                    elements.append(obj.Pop.Element.fromxmlelement(elementElement))

                return cls(taskId=taskId, messages=messages, elements=elements)
            else:
                return None

    class Info(object):
        lineMatcher = re.compile(r'^(.+):[\s]+(.+)$')

        def __init__(self, principal, host, serverName, port, dbEncoding, ACCUREV_BIN, clientTime, serverTime, clientVer=None, serverVer=None, depot=None, workspaceRef=None, basis=None, top=None):
            self.principal    = principal
            self.host         = host
            self.clientVer    = clientVer
            self.serverName   = serverName
            self.port         = port
            self.dbEncoding   = dbEncoding
            self.ACCUREV_BIN  = ACCUREV_BIN
            self.serverVer    = serverVer
            self.clientTime   = clientTime
            self.serverTime   = serverTime
            self.depot        = depot
            self.workspaceRef = workspaceRef
            self.basis        = basis
            self.top          = top

        def __repr__(self):
            str  = "Principal:      {0}\n".format(self.principal)
            str += "Host:           {0}\n".format(self.host)
            if self.clientVer is not None:
                str += "client_ver:     {0}\n".format(self.clientVer)
            str += "Server name:    {0}\n".format(self.serverName)
            str += "Port:           {0}\n".format(self.port)
            str += "DB Encoding:    {0}\n".format(self.dbEncoding)
            str += "ACCUREV_BIN:    {0}\n".format(self.ACCUREV_BIN)
            if self.serverVer is not None:
                str += "server_ver:     {0}\n".format(self.serverVer)
            str += "Client time:    {0}\n".format(self.clientTime)
            str += "Server time:    {0}\n".format(self.serverTime)
            if self.depot is not None:
                str += "Depot:          {0}\n".format(self.depot)
            if self.workspaceRef is not None:
                str += "Workspace/ref:  {0}\n".format(self.workspaceRef)
            if self.basis is not None:
                str += "Basis:          {0}\n".format(self.basis)
            if self.top is not None:
                str += "Top:            {0}\n".format(self.top)

            return str

        @classmethod
        def fromstring(cls, string):
            itemMap = {}
            lines = string.split('\n')
            for line in lines:
                match = cls.lineMatcher.search(line)
                if match:
                    itemMap[match.group(1)] = match.group(2)

            return cls(principal=itemMap["Principal"]              \
                       , host=itemMap["Host"]                      \
                       , serverName=itemMap["Server name"]         \
                       , port=itemMap.get("Port")                  \
                       , dbEncoding=itemMap.get("DB Encoding")     \
                       , ACCUREV_BIN=itemMap["ACCUREV_BIN"]        \
                       , clientTime=itemMap.get("Client time")     \
                       , serverTime=itemMap.get("Server time")     \
                       , clientVer=itemMap.get("client_ver")       \
                       , serverVer=itemMap.get("server_ver")       \
                       , depot=itemMap.get("Depot")                \
                       , workspaceRef=itemMap.get("Workspace/ref") \
                       , basis=itemMap.get("Basis")                \
                       , top=itemMap.get("Top"))



# ################################################################################################ #
# AccuRev raw commands                                                                             #
# The raw class namespaces raw accurev commands that return text output directly from the terminal #
# ################################################################################################ #
class raw(object):
    # The __lastCommand is used to access the return code that the last command had generated in most
    # cases.
    _lastCommand = None
    _accurevCmd = "accurev"
    _commandCacheFilename = None

    class CommandCache(object):
        createTableQuery = '''
CREATE TABLE IF NOT EXISTS command_cache (
  command TEXT PRIMARY KEY NOT NULL,
  result  INT NOT NULL,
  stdout  TEXT NOT NULL,
  stderr  TEXT
);
'''

        def __enter__(self):
            self.Close()
            self.Open()

            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.Close()
            return False

        def __init__(self, filepath):
            self.filepath = filepath
            self.connection = None
            self.cursor = None

        def Open(self):
            self.connection = sqlite3.connect(self.filepath)
            self.cursor = self.connection.cursor()
            self.cursor.execute(raw.CommandCache.createTableQuery)
            self.connection.commit()

        def Close(self):
            if self.cursor is not None:
                self.cursor.close()
                self.cursor = None
            if self.connection is not None:
                self.connection.close()
                self.connection = None
        
        def Get(self, cmd):
            self.cursor.execute('SELECT * FROM command_cache WHERE command = ?;', (str(cmd),))
            row = self.cursor.fetchone()
            if row is not None:
                row2 = self.cursor.fetchone()
                if row2 is not None:
                    raise Exception("Invariant violation! The cache should not contain duplicate commands!")
            return row

        def Add(self, cmd, result, stdout, stderr=None):
            self.cursor.execute('INSERT INTO command_cache (command, result, stdout, stderr) VALUES (?, ?, ?, ?);', (str(cmd), int(result), stdout, stderr))
            self.connection.commit()

        def Remove(self, cmd):
            self.cursor.execute('DELETE FROM command_cache WHERE command = ?;', (str(cmd),))
            self.connection.commit()

        def Update(self, cmd, result, stdout, stderr=None):
            self.Remove(cmd)
            self.Add(cmd=cmd, result=result, stdout=stdout, stderr=stderr)
 
    @staticmethod
    def _runCommand(cmd, outputFilename=None, useCache=False):
        outputFile = None
        
        # Try and see if we are able to use the command cache.
        if outputFilename is None and raw._commandCacheFilename is not None and useCache:
            with raw.CommandCache(raw._commandCacheFilename) as cc:
                row = cc.Get(cmd=cmd)
                if row is not None:
                    # Cache hit!
                    cmd, returncode, output, error = row
                    raw._lastCommand = None
                    return output

        if outputFilename is not None:
            outputFile = open(outputFilename, "w")
            accurevCommand = subprocess.Popen(cmd, stdout=outputFile, stdin=subprocess.PIPE, universal_newlines=False)
        else:
            accurevCommand = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, universal_newlines=False)
            
        output = ''
        error = ''
        accurevCommand.poll()
        while accurevCommand.returncode is None:
            stdoutdata, stderrdata = accurevCommand.communicate()
            error += stderrdata.decode('utf8', 'strict')
            if outputFile is None:
                output += stdoutdata.decode('utf8', 'strict')
            accurevCommand.poll()
        
        raw._lastCommand = accurevCommand

        if raw._commandCacheFilename is not None and useCache:
            with raw.CommandCache(raw._commandCacheFilename) as cc:
               cc.Add(cmd=cmd, result=accurevCommand.returncode, stdout=output, stderr=error)
        
        if outputFile is None:
            return output
        else:
            outputFile.close()
            return 'Written to ' + outputFilename

    @staticmethod
    def getAcSync():
        # http://www.accurev.com/download/ac_current_release/AccuRev_WebHelp/AccuRev_Admin/wwhelp/wwhimpl/common/html/wwhelp.htm#href=timewarp.html&single=true
        # The AC_SYNC environment variable controls whether your machine clock being out of sync with
        # the AccuRev server time generates an error or not. Allowed states:
        #   * Not set or set to ERROR   ->   an error occurs and a message appears.
        #   * Set to WARN               ->   a warning is displayed but the command executes.
        #   * Set to IGNORE             ->   no error/warning, command executes.
        return os.environ.get('AC_SYNC')
        
    @staticmethod
    def setAcSync(value):
        os.environ['AC_SYNC'] = value

    @staticmethod
    def login(username = None, password = None, persist=False):
        if username is not None and password is not None:
            cmd = [ "accurev", "login" ]
            if persist:
                cmd.append("-n")
            cmd.extend([ username, password ])

            accurevCommand = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

            output = ''
            error  = ''
            accurevCommand.poll()
            while accurevCommand.returncode is None:
                stdoutdata, stderrdata = accurevCommand.communicate()
                output += stdoutdata
                if stderrdata is not None:
                    error  += stderrdata
                accurevCommand.poll()
            
            raw._lastCommand = accurevCommand
            
            return obj.Login(errorMessage=error)
        
        return False
        
    @staticmethod
    def logout():
        accurevCommand = subprocess.Popen([ "accurev", "logout" ], universal_newlines=True)
        accurevCommand.wait()
        
        raw._lastCommand = accurevCommand
        
        return (accurevCommand.returncode == 0)

    @staticmethod
    def stat(all=False, inBackingStream=False, dispBackingChain=False, defaultGroupOnly=False
            , defunctOnly=False, absolutePaths=False, filesOnly=False, directoriesOnly=False
            , locationsOnly=False, twoLineListing=False, showLinkTarget=False, isXmlOutput=False
            , dispElemID=False, dispElemType=False, strandedElementsOnly=False, keptElementsOnly=False
            , modifiedElementsOnly=False, missingElementsOnly=False, overlapedElementsOnly=False
            , underlapedElementsOnly=False, pendingElementsOnly=False, dontOptimizeSearch=False
            , directoryTreePath=None, stream=None, externalOnly=False, showExcluded=False
            , timeSpec=None, ignorePatternsList=[], listFile=None, elementList=None, outputFilename=None):
        cmd = [ raw._accurevCmd, "stat" ]

        if all:
            cmd.append('-a')
        if inBackingStream:
            cmd.append('-b')
        if dispBackingChain:
            cmd.append('-B')
        if defaultGroupOnly:
            cmd.append('-d')
        if defunctOnly:
            cmd.append('-D')
        
        # Construct the format string
        format = '-f'

        if stream is None:
            # -fa and -fr are not supported when using -s
            if absolutePaths:
                format += 'a'
            else:
                format += 'r'
        if filesOnly:
            format += 'f'
        elif directoriesOnly:
            format += 'd'
        if showLinkTarget:
            format += 'v'
        if isXmlOutput:
            format += 'x'
        if dispElemID:
            format += 'e'
        if dispElemType:
            format += 'k'
        
        if format != '-f':
            cmd.append(format)
        
        # Mutually exclusive parameters.
        if strandedElementsOnly:
            cmd.append('-i')
        elif keptElementsOnly:
            cmd.append('-k')
        elif modifiedElementsOnly:
            cmd.append('-m')
        elif missingElementsOnly:
            cmd.append('-M')
        elif overlapedElementsOnly:
            cmd.append('-o')
        elif pendingElementsOnly:
            cmd.append('-p')
        elif underlapedElementsOnly:
            cmd.append('-U')
        elif externalOnly:
            cmd.append('-x')

        # Remaining parameters
        if dontOptimizeSearch:
            cmd.append('-O')
        if showExcluded:
            cmd.append('-X')
        if directoryTreePath is not None:
            cmd.extend([ '-R', directoryTreePath ])
        if stream is not None:
            cmd.extend([ '-s', str(stream) ])
        if timeSpec is not None:
            cmd.extend([ '-t', str(timeSpec)])
        for ignorePattern in ignorePatternsList:
            cmd.append('--ignore=\"{0}\"'.format(ignorePattern))
        
        if not all and (listFile is None and elementList is None):
            cmd.append('*')
        else:
            if listFile is not None:
                cmd.extend([ '-l', listFile ])
            if elementList is not None:
                if type(elementList) is list:
                    cmd.extend(elementList)
                else:
                    cmd.append(elementList)

        
        return raw._runCommand(cmd, outputFilename)

    # AccuRev history command
    @staticmethod
    def hist( depot=None, stream=None, timeSpec=None, listFile=None, isListFileXml=False, elementList=None
            , allElementsFlag=False, elementId=None, transactionKind=None, commentString=None, username=None
            , expandedMode=False, showIssues=False, verboseMode=False, listMode=False, showStatus=False, transactionMode=False
            , isXmlOutput=False, outputFilename=None, useCache=False):
        # Check the useCache flag for violations! It isn't safe to use the cache for commands that use the now or highest keywords!
        if useCache:
            if timeSpec is None:
                ts = None
            elif not isinstance(timeSpec, obj.TimeSpec):
                ts = obj.TimeSpec.fromstring(timeSpec)
            else:
                ts = timeSpec

            # For cache optimization convert highest and now keywords to numbers.
            if ts is not None and not ts.is_cacheable() and depot is not None:
                ts = ext.normalize_timespec(depot=depot, timeSpec=ts)

            useCache = ts is not None and ts.is_cacheable() # If both values are non-keywords, we can cache them.
            useCache = useCache and listFile is None and outputFilename is None   # Ensure that we don't have any file operations...
        
        cmd = [ raw._accurevCmd, "hist" ]

        # Interpret options
        if depot is not None:
            cmd.extend([ "-p", depot ])
        if stream is not None:
            cmd.extend([ "-s", str(stream) ])
        if timeSpec is not None:
            if type(timeSpec) is datetime.datetime:
                timeSpecStr = "{:%Y/%m/%d %H:%M:%S}".format(timeSpec)
            else:
                timeSpecStr = str(timeSpec)
            cmd.extend(["-t", str(timeSpecStr)])
        if listFile is not None:
            if isListFileXml:
                cmd.append("-Fx")
            cmd.extend([ "-l", listFile ])
        if elementList is not None:
            if type(elementList) is list:
                cmd.extend(elementList)
            else:
                cmd.append(elementList)
        if allElementsFlag:
            cmd.append("-a")
        if elementId is not None:
            cmd.extend([ "-e", str(elementId) ])
        if transactionKind is not None:
            cmd.extend([ "-k", transactionKind ])
        if commentString is not None:
            cmd.extend([ "-c", commentString ])
        if username is not None:
            cmd.extend([ "-u", username ])
        
        formatFlags = ""
        if expandedMode:
            formatFlags += "e"
        if showIssues:
            formatFlags += "i"
        if verboseMode:
            formatFlags += "v"
        if listMode:
            formatFlags += "l"
        if showStatus:
            formatFlags += "s"
        if transactionMode:
            formatFlags += "t"
        if isXmlOutput:
            formatFlags += "x"
        
        if len(formatFlags) > 0:
            cmd.append("-f{0}".format(formatFlags))
        
        return raw._runCommand(cmd, outputFilename, useCache=useCache)

    @staticmethod
    def diff( verSpec1=None, verSpec2=None, transactionRange=None, toBacking=False, toOtherBasisVersion=False, toPrevious=False
            , all=False, onlyDefaultGroup=False, onlyKept=False, onlyModified=False, onlyExtModified=False, onlyOverlapped=False, onlyPending=False
            , ignoreBlankLines=False, isContextDiff=False, informationOnly=False, ignoreCase=False, ignoreWhitespace=False, ignoreAmountOfWhitespace=False, useGUI=False
            , extraParams=None, isXmlOutput=False, useCache=False):
        # Validate the useCache command. It isn't safe to use the cache for keywords highest or now.
        if useCache:
            if transactionRange is None:
                ts = None
            elif not isinstance(transactionRange, obj.TimeSpec):
                ts = obj.TimeSpec.fromstring(transactionRange)
            else:
                ts = transactionRange
                
            useCache = ts is not None and not (isinstance(ts.start, str) or isinstance(ts.end, str)) # If both values are non-keywords, we can cache them.
            useCache = useCache and extraParams is None # I'm not sure what the purpose of extraParams is atm so disable the cache for the unknown.

        cmd = [ raw._accurevCmd, "diff" ]
        
        if all:
            cmd.append('-a')
        if onlyDefaultGroup:
            cmd.append('-d')
        if onlyKept:
            cmd.append('-k')
        elif onlyModified:
            cmd.append('-m')
        elif onlyExtModified:
            cmd.append('-n')
        if onlyOverlapped:
            cmd.append('-o')
        if onlyPending:
            cmd.append('-p')
        
        if toBacking:
            cmd.append('-b')
        
        if verSpec1 is not None:
            cmd.extend([ '-v', verSpec1 ])
        if verSpec2 is not None:
            cmd.extend([ '-V', verSpec2 ])
        if transactionRange is not None:
            cmd.extend([ '-t', transactionRange ])
        
        if isXmlOutput:
            cmd.append('-fx')
        
        if toOtherBasisVersion:
            cmd.append('-j')
        if toPrevious:
            cmd.append('-1')
        
        if ignoreBlankLines:
            cmd.append('-B')
        if isContextDiff:
            cmd.append('-c')
        if informationOnly:
            cmd.append('-i')
        if ignoreCase:
            cmd.append('-I')
        if ignoreWhitespace:
            cmd.append('-w')
        if ignoreAmountOfWhitespace:
            cmd.append('-W')
        if useGUI:
            cmd.append('-G')
        
        if extraParams is not None:
            cmd.extend([ '--', extraParams ])
        
        return raw._runCommand(cmd=cmd, useCache=useCache)
        
    # AccuRev populate command
    @staticmethod
    def pop(isRecursive=False, isOverride=False, verSpec=None, location=None, dontBuildDirTree=False, timeSpec=None, isXmlOutput=False, listFile=None, elementList=None):
        cmd = [ raw._accurevCmd, "pop" ]
        
        if isOverride:
            cmd.append("-O")
        if isRecursive:
            cmd.append("-R")
        
        if location is not None and verSpec is not None:
            cmd.extend(["-v", str(verSpec), "-L", location])
            if dontBuildDirTree:
                cmd.append("-D")
        elif location is not None or verSpec is not None:
            raise Exception("""AccuRev populate command must have either both the <ver-spec> and <location>
    supplied or neither. We can infer the <ver-spec> but <location>
    must be specified if it is provided""")
        
        if timeSpec is not None:
            if type(timeSpec) is datetime.datetime:
                timeSpecStr = "{:%Y/%m/%d %H:%M:%S}".format(timeSpec)
            else:
                timeSpecStr = str(timeSpec)
            cmd.extend(["-t", str(timeSpecStr)])
        
        if isXmlOutput:
            cmd.append("-fx")
        
        if listFile is not None:
            cmd.extend(["-l", listFile])
        if elementList is not None:
            if type(elementList) is list:
                cmd.extend(elementList)
            else:
                cmd.append(elementList)
        
        return raw._runCommand(cmd)

    # AccuRev checkout command
    @staticmethod
    def co(comment=None, selectAllModified=False, verSpec=None, isRecursive=False, transactionNumber=None, elementId=None, listFile=None, elementList=None):
        cmd = [ raw._accurevCmd, "co" ]
        
        if comment is not None:
            cmd.extend([ '-c', comment ])
        if selectAllModified:
            cmd.append('-n')
        if verSpec is not None:
            cmd.extend([ '-v', str(verSpec) ])
        if isRecursive:
            cmd.append('-R')
        if transactionNumber is not None:
            cmd.extend([ '-t', transactionNumber ])
        if elementId is not None:
            cmd.extend([ '-e', str(elementId) ])
        if listFile is not None:
            cmd.extend([ '-l', listFile ])
        if elementList is not None:
            if type(elementList) is list:
                cmd.extend(elementList)
            else:
                cmd.append(elementList)
        
        return raw._runCommand(cmd)
        
    @staticmethod
    def cat(elementId=None, element=None, depotName=None, verSpec=None, outputFilename=None, useCache=False):
        cmd = [ raw._accurevCmd, "cat" ]
        
        if verSpec is not None:
            cmd.extend([ '-v', str(verSpec) ])
        if depotName is not None:
            cmd.extend([ '-p', depotName ])
        
        if elementId is not None:
            cmd.extend([ '-e', str(elementId) ])
        elif element is not None:
            cmd.append(element)
        else:
            raise Exception('accurev cat command needs either an <element> or an <eid> to be specified')
            
        return raw._runCommand(cmd=cmd, outputFilename=outputFilename, useCache=useCache)
        
    @staticmethod
    def purge(comment=None, stream=None, issueNumber=None, elementList=None, listFile=None, elementId=None):
        cmd = [ raw._accurevCmd, "purge" ]
        
        if comment is not None:
            cmd.extend([ '-c', comment ])
        if stream is not None:
            cmd.extend([ '-s', str(stream) ])
        if issueNumber is not None:
            cmd.extend([ '-I', issueNumber ])
        if elementList is not None:
            if type(elementList) is list:
                cmd.extend(elementList)
            else:
                cmd.append(elementList)
        if listFile is not None:
            cmd.extend([ '-l', listFile ])
        if elementId is not None:
            cmd.extend([ '-e', str(elementId) ])
        
        return raw._runCommand(cmd)
    
    # AccuRev ancestor command
    @staticmethod
    def anc(element, commonAncestor=False, versionId=None, basisVersion=False, commonAncestorOrBasis=False, prevVersion=False, isXmlOutput=False):
        # The anc command determines one of the following:
        #  * the direct ancestor (predecessor) version of a particular version
        #  * the version that preceded a particular version in a specified stream
        #  * the basis version corresponding to a particular version
        #  * the common ancestor of two versions
        # In its simplest form (no command-line options), anc reports the direct ancestor of the version in
        # your workspace for the specified element.
        cmd = [ raw._accurevCmd, "anc" ]
        
        if commonAncestor:
            cmd.append('-c')
        if versionId is not None:
            cmd.extend([ '-v', versionId ])
        if basisVersion:
            cmd.append('-j')
        if commonAncestorOrBasis:
            cmd.append('-J')
        if prevVersion:
            cmd.append('-1')
        if isXmlOutput:
            cmd.append('-fx')
        
        cmd.append(element)
        
        return raw._runCommand(cmd)
    
    @staticmethod
    def chstream(stream, newBackingStream=None, timeSpec=None, newName=None):
        cmd = [ raw._accurevCmd, "chstream", "-s", str(stream) ]
        
        if newName is not None and (newBackingStream is not None or timeSpec is not None):
            raise Exception('accurev.raw.Chstream does not accept the newName parameter if any other parameter is passed!')
        else:
            if newBackingStream is not None:
                cmd.extend([ '-b', newBackingStream ])
            if timeSpec is not None:
                if type(timeSpec) is datetime.datetime:
                    timeSpecStr = "{:%Y/%m/%d %H:%M:%S}".format(timeSpec)
                else:
                    timeSpecStr = str(timeSpec)
                cmd.extend(["-t", str(timeSpecStr)])
            if newName is not None:
                renameCmd.append(newName)
            
            return raw._runCommand(cmd)
        
    @staticmethod
    def chws(workspace, newBackingStream=None, newLocation=None, newMachine=None, kind=None, eolType=None, isMyWorkspace=True, newName=None):
        cmd = [ raw._accurevCmd, "chws" ]
        
        if isMyWorkspace:
            cmd.extend([ '-w', workspace ])
        else:
            cmd.extend([ '-s', workspace ])
        
        if newBackingStream is not None:
            cmd.extend([ '-b', newBackingStream ])
        if newLocation is not None:
            cmd.extend([ '-l', newLocation ])
        if newMachine is not None:
            cmd.extend([ '-m', newMachine ])
        if kind is not None:
            cmd.extend([ '-k', kind ])
        if eolType is not None:
            cmd.extend([ '-e', eolType ])
        if newName is not None:
            renameCmd.append(newName)
        
        return raw._runCommand(cmd)
        
    @staticmethod
    def update(refTree=None, doPreview=False, transactionNumber=None, mergeOnUpdate=False, isXmlOutput=False, isOverride=False, outputFilename=None):
        cmd = [ raw._accurevCmd, "update" ]
        
        if refTree is not None:
            cmd.extend([ '-r', refTree ])
        if doPreview:
            cmd.append('-i')
        if transactionNumber is not None:
            cmd.extend([ '-t', transactionNumber ])
        if mergeOnUpdate:
            cmd.append('-m')
        if isXmlOutput:
            cmd.append('-fx')
        if isOverride:
            cmd.append('-O')
        
        return raw._runCommand(cmd, outputFilename)

    @staticmethod
    def info(showVersion=False):
        cmd = [ raw._accurevCmd, "info" ]

        if showVersion:
            cmd.append('-v')

        return raw._runCommand(cmd)
        
    class show(object):
        @staticmethod
        def _getShowBaseCommand(isXmlOutput=False, includeDeactivatedItems=False, includeOldDefinitions=False, addKindColumnForUsers=False, includeHasDefaultGroupAttribute=False):
            # See: http://www.accurev.com/download/ac_current_release/AccuRev_WebHelp/wwhelp/wwhimpl/js/html/wwhelp.htm#href=AccuRev_User_CLI/cli_ref_show.html
            # for usage.
            cmd = [ raw._accurevCmd, "show" ]
            
            flags = ''
            
            if includeDeactivatedItems and includeOldDefinitions:
                flags += 'I'
            elif includeDeactivatedItems:
                flags += 'i'
            
            if addKindColumnForUsers:
                flags += 'v'
            
            if includeHasDefaultGroupAttribute:
                # This option forces the XML output.
                flags += 'xg'
            elif isXmlOutput:
                flags += 'x'
            
            if len(flags) > 0:
                cmd.append('-f{0}'.format(flags))
            
            return cmd
    
        @staticmethod
        def _runSimpleShowSubcommand(subcommand, isXmlOutput=False, includeDeactivatedItems=False, includeOldDefinitions=False, addKindColumnForUsers=False, includeHasDefaultGroupAttribute=False):
            if subcommand is not None:
                cmd = raw.show._getShowBaseCommand(isXmlOutput=isXmlOutput, includeDeactivatedItems=includeDeactivatedItems, includeOldDefinitions=includeOldDefinitions, addKindColumnForUsers=addKindColumnForUsers, includeHasDefaultGroupAttribute=includeHasDefaultGroupAttribute)
                cmd.append(subcommand)
                return raw._runCommand(cmd)
                
            return None
    
        @staticmethod
        def users(isXmlOutput=False, includeDeactivatedItems=False, addKindColumnForUsers=False):
            return raw.show._runSimpleShowSubcommand(subcommand="users", isXmlOutput=isXmlOutput, includeDeactivatedItems=includeDeactivatedItems, addKindColumnForUsers=addKindColumnForUsers)
        
        @staticmethod
        def depots(isXmlOutput=False, includeDeactivatedItems=False):
            return raw.show._runSimpleShowSubcommand(subcommand="depots", isXmlOutput=isXmlOutput, includeDeactivatedItems=includeDeactivatedItems)

        @staticmethod
        def streams(depot=None, timeSpec=None, stream=None, matchType=None, listFile=None, listPathAndChildren=False, listChildren=False, listImmediateChildren=False, nonEmptyDefaultGroupsOnly=False, isXmlOutput=False, includeDeactivatedItems=False, includeOldDefinitions=False, includeHasDefaultGroupAttribute=False, useCache=False):
            # Analise the useCache variable and make sure that we can use the cache for this command!
            # For commands that use the 'now' or 'highest' keywords we can't use it (which is also implied with a timeSpec of None).
            if useCache:
                if not isinstance(timeSpec, obj.TimeSpec):
                    ts = obj.TimeSpec.fromstring(timeSpec)
                else:
                    ts = timeSpec

                useCache = ts is not None and ts.is_cacheable() and listFile is None # Ensure that we don't have any file operations...

            cmd = raw.show._getShowBaseCommand(isXmlOutput=isXmlOutput, includeDeactivatedItems=includeDeactivatedItems, includeOldDefinitions=includeOldDefinitions, includeHasDefaultGroupAttribute=includeHasDefaultGroupAttribute)

            if depot is not None:
                cmd.extend([ "-p", depot ])
            if timeSpec is not None:
                if type(timeSpec) is datetime.datetime:
                    timeSpecStr = "{:%Y/%m/%d %H:%M:%S}".format(timeSpec)
                else:
                    timeSpecStr = str(timeSpec)
                cmd.extend(["-t", str(timeSpecStr)])
            if stream is not None:
                cmd.extend([ "-s", str(stream) ])
            if matchType is not None:
                cmd.extend([ "-m", matchType ])
            if listFile is not None:
                cmd.extend([ "-l", listFile ])
            
            if listPathAndChildren:
                cmd.append("-r")
            elif listChildren:
                cmd.append("-R")
            elif listImmediateChildren:
                cmd.append("-1")
                
            cmd.append("streams")
            
            return raw._runCommand(cmd=cmd, useCache=useCache)
    
    class replica(object):
        @staticmethod
        def sync():
            cmd = [ raw._accurevCmd, "replica", "sync" ]
            
            return raw._runCommand(cmd)
    
# ################################################################################################ #
# Script Functions (the main interface to this library)                                            #
# ################################################################################################ #
def getAcSync():
    return raw.getAcSync()
        
def setAcSync(value):
    raw.setAcSync(value)

def login(username = None, password = None):
    return raw.login(username, password)
    
def logout():
    return raw.logout()

def stat(all=False, inBackingStream=False, dispBackingChain=False, defaultGroupOnly=False
        , defunctOnly=False, absolutePaths=False, filesOnly=False, directoriesOnly=False
        , locationsOnly=False, twoLineListing=False, showLinkTarget=False
        , dispElemID=False, dispElemType=False, strandedElementsOnly=False, keptElementsOnly=False
        , modifiedElementsOnly=False, missingElementsOnly=False, overlapedElementsOnly=False
        , underlapedElementsOnly=False, pendingElementsOnly=False, dontOptimizeSearch=False
        , directoryTreePath=None, stream=None, externalOnly=False, showExcluded=False
        , timeSpec=None, ignorePatternsList=[], listFile=None, elementList=None, outputFilename=None):
    outputXml = raw.stat(all=all, inBackingStream=inBackingStream, dispBackingChain=dispBackingChain, defaultGroupOnly=defaultGroupOnly
        , defunctOnly=defunctOnly, absolutePaths=absolutePaths, filesOnly=filesOnly, directoriesOnly=directoriesOnly
        , locationsOnly=locationsOnly, twoLineListing=twoLineListing, showLinkTarget=showLinkTarget, isXmlOutput=True
        , dispElemID=dispElemID, dispElemType=dispElemType, strandedElementsOnly=strandedElementsOnly, keptElementsOnly=keptElementsOnly
        , modifiedElementsOnly=modifiedElementsOnly, missingElementsOnly=missingElementsOnly, overlapedElementsOnly=overlapedElementsOnly
        , underlapedElementsOnly=underlapedElementsOnly, pendingElementsOnly=pendingElementsOnly, dontOptimizeSearch=dontOptimizeSearch
        , directoryTreePath=directoryTreePath, stream=stream, externalOnly=externalOnly, showExcluded=showExcluded
        , timeSpec=timeSpec, ignorePatternsList=ignorePatternsList, listFile=listFile, elementList=elementList, outputFilename=outputFilename)
    if raw._lastCommand.returncode == 0:
        return obj.Stat.fromxmlstring(outputXml)
    else:
        return None

# AccuRev history command
def hist( depot=None, stream=None, timeSpec=None, listFile=None, isListFileXml=False, elementList=None
        , allElementsFlag=False, elementId=None, transactionKind=None, commentString=None, username=None
        , expandedMode=True, showIssues=False, verboseMode=False, listMode=False, showStatus=False, transactionMode=False
        , outputFilename=None, useCache=False):
    xmlOutput = raw.hist(depot=depot, stream=stream, timeSpec=timeSpec, listFile=listFile, isListFileXml=isListFileXml, elementList=elementList
        , allElementsFlag=allElementsFlag, elementId=elementId, transactionKind=transactionKind, commentString=commentString, username=username
        , expandedMode=expandedMode, showIssues=showIssues, verboseMode=verboseMode, listMode=listMode, showStatus=showStatus, transactionMode=transactionMode
        , isXmlOutput=True, outputFilename=outputFilename, useCache=useCache)
    return obj.History.fromxmlstring(xmlOutput)

# AccuRev diff command
def diff(verSpec1=None, verSpec2=None, transactionRange=None, toBacking=False, toOtherBasisVersion=False, toPrevious=False
        , all=False, onlyDefaultGroup=False, onlyKept=False, onlyModified=False, onlyExtModified=False, onlyOverlapped=False, onlyPending=False
        , ignoreBlankLines=False, isContextDiff=False, informationOnly=False, ignoreCase=False, ignoreWhitespace=False, ignoreAmountOfWhitespace=False, useGUI=False
        , extraParams=None, useCache=False):
    xmlOutput = raw.diff(verSpec1=verSpec1, verSpec2=verSpec2, transactionRange=transactionRange, toBacking=toBacking, toOtherBasisVersion=toOtherBasisVersion, toPrevious=toPrevious
        , all=all, onlyDefaultGroup=onlyDefaultGroup, onlyKept=onlyKept, onlyModified=onlyModified, onlyExtModified=onlyExtModified, onlyOverlapped=onlyOverlapped, onlyPending=onlyPending
        , ignoreBlankLines=ignoreBlankLines, isContextDiff=isContextDiff, informationOnly=informationOnly, ignoreCase=ignoreCase, ignoreWhitespace=ignoreWhitespace, ignoreAmountOfWhitespace=ignoreAmountOfWhitespace, useGUI=useGUI
        , extraParams=extraParams, isXmlOutput=True, useCache=useCache)
    return obj.Diff.fromxmlstring(xmlOutput)

# AccuRev Populate command
def pop(isRecursive=False, isOverride=False, verSpec=None, location=None, dontBuildDirTree=False, timeSpec=None, listFile=None, elementList=None):
    output = raw.pop(isRecursive=isRecursive, isOverride=isOverride, verSpec=verSpec, location=location, dontBuildDirTree=dontBuildDirTree, timeSpec=timeSpec, isXmlOutput=True, listFile=listFile, elementList=elementList)
    return obj.Pop.fromxmlstring(output)

# AccuRev checkout command
def co(comment=None, selectAllModified=False, verSpec=None, isRecursive=False, transactionNumber=None, elementId=None, listFile=None, elementList=None):
    output = raw.oo(comment=comment, selectAllModified=selectAllModified, verSpec=verSpec, isRecursive=isRecursive, transactionNumber=transactionNumber, elementId=elementId, listFile=listFile, elementList=elementList)
    if raw._lastCommand is not None:
        return (raw._lastCommand.returncode == 0)
    return None

def cat(elementId=None, element=None, depotName=None, verSpec=None, outputFilename=None, useCache=False):
    if useCache:
        useCache = useCache and outputFilename is None
    output = raw.cat(elementId=elementId, element=element, depotName=depotName, verSpec=verSpec, outputFilename=outputFilename, useCache=useCache)
    if raw._lastCommand is not None:
        return output
    return None

def purge(comment=None, stream=None, issueNumber=None, elementList=None, listFile=None, elementId=None):
    output = raw.purge(comment=comment, stream=stream, issueNumber=issueNumber, elementList=elementList, listFile=listFile, elementId=elementId)
    if raw._lastCommand is not None:
        return (raw._lastCommand.returncode == 0)
    return None

# AccuRev ancestor command
def anc(element, commonAncestor=False, versionId=None, basisVersion=False, commonAncestorOrBasis=False, prevVersion=False):
    outputXml = raw.anc(element, commonAncestor=False, versionId=None, basisVersion=False, commonAncestorOrBasis=False, prevVersion=False, isXmlOutput=True)
    return obj.Ancestor.fromxmlstring(outputXml)
    
def chstream(stream, newBackingStream=None, timeSpec=None, newName=None):
    raw.chstream(stream=stream, newBackingStream=newBackingStream, timeSpec=timeSpec, newName=newName)
    if raw._lastCommand is not None:
        return (raw._lastCommand.returncode == 0)
    return None
    
def chws(workspace, newBackingStream=None, newLocation=None, newMachine=None, kind=None, eolType=None, isMyWorkspace=True, newName=None):
    raw.chws(workspace=workspace, newBackingStream=newBackingStream, newLocation=newLocation, newMachine=newMachine, kind=kind, eolType=eolType, isMyWorkspace=isMyWorkspace, newName=newName)
    if raw._lastCommand is not None:
        return (raw._lastCommand.returncode == 0)
    return None
        
def update(refTree=None, doPreview=False, transactionNumber=None, mergeOnUpdate=False, isOverride=False, outputFilename=None):
    outputXml = raw.update(refTree=refTree, doPreview=doPreview, transactionNumber=transactionNumber, mergeOnUpdate=mergeOnUpdate, isXmlOutput=True, isOverride=isOverride, outputFilename=outputFilename)
    return obj.Update.fromxmlstring(outputXml)
    
def info(showVersion=False):
    outputString = raw.info(showVersion=showVersion)
    return obj.Info.fromstring(outputString)
        
class show(object):
    @staticmethod
    def users():
        xmlOutput = raw.show.users(isXmlOutput=True)
        return obj.Show.Users.fromxmlstring(xmlOutput)
    
    @staticmethod
    def depots(includeDeactivatedItems=False):
        xmlOutput = raw.show.depots(includeDeactivatedItems=includeDeactivatedItems, isXmlOutput=True)
        return obj.Show.Depots.fromxmlstring(xmlOutput)

    @staticmethod
    def streams(depot=None, timeSpec=None, stream=None, matchType=None, listFile=None, listPathAndChildren=False, listChildren=False, listImmediateChildren=False, nonEmptyDefaultGroupsOnly=False, includeDeactivatedItems=False, includeOldDefinitions=False, includeHasDefaultGroupAttribute=False, useCache=False):
        if useCache:
            if not isinstance(timeSpec, obj.TimeSpec):
                ts = obj.TimeSpec.fromstring(timeSpec)
            else:
                ts = timeSpec

            useCache = ts is not None and ts.is_cacheable() and listFile is None # Ensure that we don't have any file operations...
            
        if useCache and depot is not None and stream is not None and isinstance(stream, int):
            # At this point we know that the command is cache-able. Here we try and maximize the use of the cache for the 'stream' argument.
            # For stream numbers it is safe to optimize the cache by getting all the streams at this transaction (which will be a single
            # cache entry) and then filtering the result to look like it would as if we only queried accurev for the specified stream.
            # Warning: This only works for stream id's (stream numbers) since the command does some magical things with renamed streams!
            #          A stream can be queried by any of its past names by using this command at any point in time but its returned name
            #          is as it was at the particular transaction. This means that if we only have the name and the stream was renamed we may
            #          not be able to figure out which stream the user is trying to get. Hence the isinstance(stream, int) condition!!!
            xmlOutput = raw.show.streams(depot=depot, timeSpec=timeSpec, stream=None, matchType=matchType, listFile=listFile, listPathAndChildren=listPathAndChildren, listChildren=listChildren, listImmediateChildren=listImmediateChildren, nonEmptyDefaultGroupsOnly=nonEmptyDefaultGroupsOnly, isXmlOutput=True, includeDeactivatedItems=includeDeactivatedItems, includeOldDefinitions=includeOldDefinitions, includeHasDefaultGroupAttribute=includeHasDefaultGroupAttribute, useCache=useCache)
            
            rvObj = obj.Show.Streams.fromxmlstring(xmlOutput)
            if rvObj is not None:
                s = rvObj.getStream(stream)
                if s is not None:
                    rvObj.streams = [ s ]
                    return rvObj

        xmlOutput = raw.show.streams(depot=depot, timeSpec=timeSpec, stream=stream, matchType=matchType, listFile=listFile, listPathAndChildren=listPathAndChildren, listChildren=listChildren, listImmediateChildren=listImmediateChildren, nonEmptyDefaultGroupsOnly=nonEmptyDefaultGroupsOnly, isXmlOutput=True, includeDeactivatedItems=includeDeactivatedItems, includeOldDefinitions=includeOldDefinitions, includeHasDefaultGroupAttribute=includeHasDefaultGroupAttribute, useCache=useCache)
        return obj.Show.Streams.fromxmlstring(xmlOutput)

class replica(object):
    @staticmethod
    def sync():
        raw.replica.sync()
        if raw._lastCommand is not None:
            return (raw._lastCommand.returncode == 0)
        return None
        
# ################################################################################################ #
# AccuRev Command Extensions                                                                       #
# ################################################################################################ #
class ext(object):
    @staticmethod
    def is_loggedin(infoObj=None):
        if infoObj is None:
            infoObj = info()
        return (infoObj.principal != "(not logged in)")

    @staticmethod
    def enable_command_cache(cacheFilename):
        raw._commandCacheFilename = cacheFilename

    @staticmethod
    def disable_command_cache():
        raw._commandCacheFilename = None



    # Get the mkstream transaction for the stream. This can sometimes be a non-trivial operation depending on how old the depot is (version of accurev).
    @staticmethod
    def get_mkstream_transaction(stream, depot=None, useCache=False):
        mkstreamTr = None

        # Since we don't know if this stream has been renamed in the past, we can't optimize this for the cache
        # like we do subsequently (by using Show.Streams(obj).getStream()).
        streamInfo = show.streams(depot=depot, stream=stream, useCache=useCache).streams[0]
        if depot is None:
            depot = streamInfo.depotName

        # Next, we need to ensure that we don't query things before the stream existed.
        if streamInfo.streamNumber == 1:
            # Assumptions:
            #   - The depot name matches the root stream name
            #   - The root stream number is always 1.
            #   - There is no mkstream transaction for the root stream.
            firstTr = hist(depot=depot, timeSpec="1", useCache=useCache)
            if firstTr is None or len(firstTr.transactions) == 0:
                raise Exception("Error: assumption that the root stream has the same name as the depot doesn't hold. Aborting...")
            mkstreamTr = firstTr.transactions[0]
        else:
            mkstream = hist(stream=stream, transactionKind="mkstream", timeSpec="highest", useCache=useCache)
            if mkstream is None or len(mkstream.transactions) == 0:
                # Warning: if you are unlucky enough to hit this path, it is really, really slow... Probably can be optimized but doesn't happen often enough for me to do it.

                # The root stream has no mkstream transaction and it has a stream number of 1. However, I have found that other streams
                # can also have a missing mkstream transaction (one that doesn't appear in the `accurev hist` output) for old depots that
                # have seen a number of upgrades. In this case we should find the mkstream transaction by looking at the startTime of a stream.
                # We have no choice but to continue querying accurev here if we want to be correct.

                # We need to find the mkstream transaction that occurred at the time when this stream was created. The `accurev show streams -fx`
                # command returns a `startTime=...` attribute which corresponds to the the timestamp of the last chstream or mkstream transaction.
                # so what we will do is to find the first transaction that we do have a record of on this stream, we will then get the result of
                # the `accurev show streams -s <stream> -t <first-transaction>` to get the correct `startTime=...` which will identify which mkstream
                # transaction corresponds to this stream.

                # Get the stream's information just before the first chstream transaction for this stream, which will by assumption have the `startTime` for the mkstream transaction.
                chstreams = hist(depot=depot, timeSpec="highest-1", stream=streamInfo.name, transactionKind="chstream", useCache=useCache) # chstreams are rare so this should be quicker than looking for everything.
                mkstreamsTimeSpecStr = "highest-1"
                if chstreams is not None and len(chstreams.transactions) > 0:
                    firstChstreamTr = chstreams.transactions[-1]
                    # Update the stream data from the time of the first transaction which will give us the correct startTime.
                    streamInfo = show.streams(depot=depot, timeSpec=(firstChstreamTr.id - 1), stream=stream).streams[0]
                    mkstreamsTimeSpecStr = "{trId}-1".format(trId=firstChstreamTr.id - 1)

                # Get all the mkstream transactions before the first transaction on this stream.
                mkstreams = hist(depot=depot, timeSpec=mkstreamsTimeSpecStr, transactionKind="mkstream", useCache=useCache)

                mkstreamTrList = []
                for t in mkstreams.transactions:
                    if GetTimestamp(t.time) == GetTimestamp(streamInfo.startTime):
                        mkstreamTrList.append(t)
                    elif GetTimestamp(t.time) < GetTimestamp(streamInfo.startTime):
                        break # There's no point in looking for it any further than this since the transactions are sorted in descending order of transaction number and hence by time as well.
                
                if len(mkstreamTrList) == 1:
                    mkstreamTr = mkstreamTrList[0]
                elif len(mkstreamTrList) > 1:
                    # You're really, really unlucky here.
                    for t in mkstreamTrList:
                        before = show.streams(depot=depot, timeSpec=(t.id - 1)).getStream(streamInfo.streamNumber)
                        after = show.streams(depot=depot, timeSpec=(t.id)).getStream(streamInfo.streamNumber)
                        if before is None and after is not None:
                            mkstreamTr = t
                            break
                if mkstreamTr is None:
                    # Failed to find the mkstream transaction.
                    return None
            else:
                # We found the mkstream transaction cheaply, return it.
                mkstreamTr = mkstream.transactions[0]
                if len(mkstream.transactions) != 1:
                    # There seem to be multiple mkstream transactions for this stream.
                    # Since we can't know which one belongs to us, return.
                    return None

        return mkstreamTr

    # Get the last chstream transaction. If no chstream transactions have been made the mkstream
    # transaction is returned. If no mkstream transaction exists None is returned.
    # returns obj.Transaction
    @staticmethod
    def stream_info(stream, transaction, useCache=False):
        # As of AccuRev 4.7.2, the data stored in the database by the mkstream command includes the stream-ID. 
        # Streams and workspaces created after installing 4.7.2 will display this additional stream information 
        # as part of the hist command.
        timeSpec = '{0}-1.1'.format(transaction)
        history = hist(stream=stream, timeSpec=timeSpec, transactionKind='chstream', useCache=useCache)
        
        if history is not None and history.transactions is not None and len(history.transactions) > 0:
            return history.transactions[0]
        
        history = hist(stream=stream, timeSpec=timeSpec, transactionKind='mkstream', useCache=useCache)

        if history is not None and history.transactions is not None and len(history.transactions) > 0:
            return history.transactions[0]
        
        return None
    
    # Returns a dictionary where the keys are the stream names and the values are obj.Stream objects.
    @staticmethod
    def stream_dict(depot, transaction, useCache=False):
        streams = show.streams(depot=depot, timeSpec='{0}'.format(transaction), useCache=useCache)
        streamDict = None
        if streams is not None:
            streams = streams.streams
            if streams is not None:
                streamDict = {}
                for s in streams:
                    streamDict[s.name] = s

        return streamDict

    # Returns a list of parents of the given stream in the following format
    #   [ stream, parent, parent's parent, ... ]
    # where each item in the list is an object of type obj.Stream
    @staticmethod
    def stream_parent_list(depot, stream, transaction, useCache=False):
        streamDict = ext.stream_dict(depot=depot, transaction=transaction, useCache=useCache)

        if stream not in streamDict:
            raise Exception('Unhandled error: stream either doesn\'t exist or has changed names in this transaction range')

        parentNames = [ stream ]
        while parentNames[-1] is not None:
            if parentNames[-1] in streamDict:
                basis = streamDict[parentNames[-1]].basis
                parentNames.append(basis) # terminating condition is when the basis is None
            else:
                break

        parentNames.pop()
        
        parentObjects = []
        for parentName in parentNames:
            parentObjects.append(streamDict[parentName])

        return parentObjects

    @staticmethod
    def normalize_timespec(depot, timeSpec):
        if isinstance(timeSpec, obj.TimeSpec):
            ts = timeSpec
        elif isinstance(timeSpec, str):
            ts = obj.TimeSpec.fromstring(timeSpec)
        else:
            raise Exception("Unrecognized time-spec type {0}".format(type(timeSpec)))

        # Normalize the timeSpec
        # ======================
        #   1. Change the accurev keywords (e.g. highest, now) and dates into transaction numbers:
        #      Note: The keywords highest/now are translated w.r.t. the depot and not the stream.
        #            Otherwise we might miss later promotes to parent streams...
        if not isinstance(ts.start, int) and ts.start is not None:
            startHistory = hist(depot=depot, timeSpec=ts.start, useCache=False)
            if startHistory is not None and startHistory.transactions is not None and len(startHistory.transactions) > 0:
                ts.start = startHistory.transactions[0].id
        if not isinstance(ts.end, int) and ts.end is not None:
            endHistory = hist(depot=depot, timeSpec=ts.end, useCache=False)
            if endHistory is not None and endHistory.transactions is not None and len(endHistory.transactions) > 0:
                ts.end = endHistory.transactions[0].id
        #   2. If there is a limit set on the number of transactions convert it into a start and end without a limit...
        if ts.start is not None and ts.end is not None and ts.limit is not None:
            if ts.end is None or abs(ts.end - ts.start + 1) > ts.limit:
                if ts.end > ts.start:
                    ts.end = ts.start - ts.limit + 1
                else:
                    ts.start = ts.end - ts.limit + 1
            ts.limit = None
        elif ts.end is None:
            ts.end = ts.start

        return ts

    @staticmethod
    def restrict_timespec_to_timelock(depot=None, timeSpec=None, timelock=None):
        if timeSpec is not None and timelock is not None:
            # Validate timelock
            timelock = UTCDateTimeOrNone(timelock)
            if timelock is None:
                return timeSpec # Timelock won't have any affect on the timeSpec.
            timelock = GetTimestamp(timelock)
            if timelock == 0:
                return timeSpec # Timelock won't have any affect on the timeSpec

            if depot is None:
                if not (isinstance(timeSpec.start, datetime.datetime) and isinstance(timeSpec.end, datetime.datetime)):
                    raise Exception("Argument error! depot is required for non-time based timelocks!")
                # Here we are dealing with simple date times that must be less than a range.
                if timelock < GetTimestamp(timeSpec.start):
                    return None # This timeSpec is after the timelock in its entirety.
                elif timelock < GetTimestamp(timeSpec.end):
                    timeSpec.end = UTCDateTimeOrNone(timelock)
            else:
                # Here we must figure out what transaction range is before the timelock.
                timeSpec = ext.normalize_timespec(depot=depot, timeSpec=timeSpec)
                if timeSpec is not None:
                    # Ensure ascending order for the timespec.
                    isAsc = timeSpec.is_asc()
                    if not isAsc:
                        # Make descending
                        timeSpec = timeSpec.reversed()
                    # Get the transaction number at the given time.
                    preLockHistory = hist(depot=depot, timeSpec=UTCDateTimeOrNone(timelock))
                    if preLockHistory is None or preLockHistory.transactions is None or len(preLockHistory.transactions) == 0:
                        return None
                    preLockTr = preLockHistory.transactions[0]
                    if preLockTr is None or timeSpec.start > preLockTr.id + 1:
                        return None
                    elif timeSpec.end > preLockTr.id:
                        timeSpec.end = preLockTr.id

                    if not isAsc:
                        timeSpec = timeSpec.reversed()

        return timeSpec

    @staticmethod
    # Retrieves a list of _all transactions_ which affect the given stream, directly or indirectly (via parent promotes).
    # Returns a list of obj.Transaction(object) types.
    def deep_hist(depot=None, stream=None, timeSpec='now', ignoreTimelocks=False, useCache=False):
        # Validate arguments
        # ==================
        if stream is None:
            # When the stream is not specified then we just want all the depot transactions for the given time-spec.
            return hist(depot=depot, timeSpec=timeSpec, useCache=useCache)

        if isinstance(timeSpec, obj.TimeSpec):
            ts = timeSpec
        elif isinstance(timeSpec, str):
            ts = obj.TimeSpec.fromstring(timeSpec)
        else:
            raise Exception("Unrecognized time-spec type {0}".format(type(timeSpec)))

        # Since we don't know if this stream has been renamed in the past, we can't optimize this for the cache
        # like we do subsequently (by using Show.Streams(obj).getStream()).
        showStreams = show.streams(stream=stream, useCache=useCache)
        if showStreams is not None and showStreams.streams is not None and len(showStreams.streams) > 0:
            streamInfo = show.streams(stream=stream, useCache=useCache).streams[0]
        else:
            raise Exception("Error: assumption that the show streams returns a list doesn't hold. Aborting...")

        # Normalize the timeSpec
        # ======================
        ts = ext.normalize_timespec(depot=streamInfo.depotName, timeSpec=timeSpec)

        # Additionally we must ensure that the transactions are traversed in ascending order.
        isAsc = ts.is_asc()
        if not isAsc:
            # Make descending
            ts = ts.reversed()

        # Next, we need to ensure that we don't query things before the stream existed.
        if streamInfo.streamNumber == 1:
            # Assumptions:
            #   - The depot name matches the root stream name
            #   - The root stream number is always 1.
            #   - There is no mkstream transaction for the root stream.
            firstTr = hist(depot=depot, timeSpec="1", useCache=useCache)
            if firstTr is None or firstTr.transactions is None or len(firstTr.transactions) == 0:
                raise Exception("Error: assumption that the root stream has the same name as the depot doesn't hold. Aborting...")
            mkstreamTr = firstTr.transactions[0]
        else:
            mkstreamTr = ext.get_mkstream_transaction(stream=streamInfo.name, depot=depot, useCache=useCache)
            if mkstreamTr is None:
                mkstreamTr = ext.get_mkstream_transaction(stream=streamInfo.streamNumber, depot=depot, useCache=useCache)
                if mkstreamTr is None:
                    # We can't reasonably determine where the stream started so just pick the first transaction
                    # from the stream itself.
                    h = hist(depot=depot, timeSpec="highest-1", stream=streamInfo.name, useCache=useCache)
                    if h is not None and len(h.transactions) > 0:
                        mkstreamTr = h.transactions[-1] # Get first transaction
                    else:
                        return []
            if mkstreamTr.id > ts.end:
                # The stream didn't exist during the requested time span.
                return []

        if ts.start < mkstreamTr.id:
            if ts.end < mkstreamTr.id:
                return [] # Nothing to be done here. The stream doesn't exist in the range.
            else:
                ts.start = mkstreamTr.id

        # Special case: Accurev pass-through stream
        # -----------------------------------------
        # Here we will only restrict the timeSpec to be after the pass-through stream was created and return the history of the parent
        # stream instead with an early return.
        if streamInfo.Type == "passthrough":
            if streamInfo.basisStreamNumber is None:
                return []

            rv = ext.deep_hist(depot=depot, stream=streamInfo.basis, timeSpec=ts, ignoreTimelocks=ignoreTimelocks, useCache=useCache)
            if not isAsc:
                rv.reverse()

            return rv

        #print('{0}:{1}'.format(stream, ts)) # debug info

        # Perform deep-hist algorithm
        # ===========================
        # The transaction list that combines all of the transactions which affect this stream.
        trList = []

        # Get the history for the requested stream in the requested transaction range _ts_.
        history = hist(depot=depot, stream=stream, timeSpec=str(ts), useCache=useCache)

        # This is the core algorithm. Here we look for `chstream` transactions and _timelocks_ which affect
        # the result of a deep history inspection.
        prevTr = None
        parentTs = ts
        for tr in history.transactions:
            if tr.Type == "chstream" and streamInfo.Type != "snapshot":
                # Parent stream has potentially changed. Here we will split the history into before and after the `chstream` transaction.
                # For the _before_ part we will recursively run the deep-hist algorithm on our entire parent hierarchy and record the
                # _after_ part in the _parentTs_ variable as a time-spec.
                # Spacial case: Accurev snapshot streams
                # --------------------------------------
                #   A "snapshot" is an immutable (“frozen”, “static”) stream that captures the configuration of another stream at a
                #   particular time. A snapshot cannot be renamed or modified in any way. Hence there is no need to recursively
                #   search the history of our parents.
                if prevTr is not None:
                    # Add the parent stream's history to our own, recursively up the parent chain,
                    # for all of the transactions leading up to this `chstream` transaction.
                    parentTs = obj.TimeSpec(start=parentTs.start, end=(tr.id - 1))
                    showStreams = show.streams(depot=depot, stream=streamInfo.streamNumber, timeSpec=parentTs.start, useCache=useCache)
                    if showStreams is not None and showStreams.streams is not None and len(showStreams.streams) > 0:
                        streamInfo = showStreams.streams[0]
                        parentStream = streamInfo.basis
                        if parentStream is not None:
                            timelockTs = parentTs
                            if not ignoreTimelocks:
                                # If we are told to respect timelocks we need to make sure to adjust our time-spec to exclude any transactions that
                                # the timelock would exclude. Sadly we need to manually model what Accurev does for timelocks in this command.
                                # We only account for timelocks on the stream we are processing. The parent stream timelocks will be dealt with
                                # through recursive invocations of this function.
                                timelockTs = ext.restrict_timespec_to_timelock(depot=streamInfo.depotName, timeSpec=parentTs, timelock=streamInfo.time)

                            # A None value for the _timelockTs_ indicates that the entire timespec is after the timelock, meaning that there are no useful transactions to process.
                            if timelockTs is not None:
                                # If there are useful transactions to process we will call deep_hist() on our parent stream and include the list of transactions returned
                                # into our result.
                                parentTrList = ext.deep_hist(depot=depot, stream=parentStream, timeSpec=timelockTs, ignoreTimelocks=ignoreTimelocks, useCache=useCache)
                                trList.extend(parentTrList)
                    # Here everything before the `chstream` transaction has already been processed with the deep-hist algorithm for all parents in the hierarchy
                    # and so we only need to run deep_hist() on our parent hierarchy for the remaining transactions, which are recorded in the _parentTs_ variable.
                    parentTs = obj.TimeSpec(start=tr.id, end=ts.end)

            trList.append(tr)
            prevTr = tr

        # Run the deep-hist algorithm on our parent stream (except if we are a snapshot stream) for the time-spec in _parentTs_ which represents
        # either the whole time-spec - if no `chstream` transactions occurred in the range - or the time-spec from the last `chstream` transaction
        # to the end of the original time-spec range.
        showStreams = show.streams(depot=depot, stream=streamInfo.streamNumber, timeSpec=parentTs.start, useCache=useCache)
        if showStreams is not None and showStreams.streams is not None and len(showStreams.streams) > 0:
            streamInfo = showStreams.streams[0]
            parentStream = streamInfo.basis
            if parentStream is not None and streamInfo.Type != "snapshot":
                timelockTs = parentTs
                if not ignoreTimelocks:
                    timelockTs = ext.restrict_timespec_to_timelock(depot=streamInfo.depotName, timeSpec=parentTs, timelock=streamInfo.time)
                if timelockTs is not None: # A None value indicates that the entire timespec is after the timelock.
                    parentTrList = ext.deep_hist(depot=depot, stream=parentStream, timeSpec=timelockTs, ignoreTimelocks=ignoreTimelocks, useCache=useCache)
                    trList.extend(parentTrList)

        rv = sorted(trList, key=lambda tr: tr.id)
        # Depending on the ordering of the provided time-spec return the transactions in the expected order (ascending/descending)
        if not isAsc:
            rv.reverse()

        return rv

    @staticmethod
    # Returns a list of streams which are affected by the given transaction.
    # The transaction must be of type obj.Transaction which is obtained from the obj.History.transactions
    # which is returned by the hist() function.
    def affected_streams(depot, transaction, includeWorkspaces=True, ignoreTimelocks=False, doDiffs=False, useCache=False):
        if not isinstance(transaction, obj.Transaction):
            transactionHist = hist(depot=depot, timeSpec=str(transaction), useCache=useCache)
            if transactionHist is not None and transactionHist.transactions is not None and len(transactionHist.transactions) > 0:
                transaction = transactionHist.transactions[0]
            else:
                return None
        
        rv = None

        destStreamNum = transaction.affectedStream()[1]
        showStreams = show.streams(depot=depot, stream=destStreamNum, timeSpec=transaction.id, useCache=useCache)
        if showStreams is not None and showStreams.streams is not None and len(showStreams.streams) > 0:
            destStream = showStreams.streams[0].name

        if destStream is not None:
            streamMap = ext.stream_dict(depot=depot, transaction=transaction.id, useCache=useCache)

            childrenSet = set()
            newChildrenSet = set()

            newChildrenSet.add(destStream)
            while len(newChildrenSet) > 0:
                childrenSet |= newChildrenSet
                newChildrenSet = set()

                for stream in streamMap:
                    if streamMap[stream].basis in childrenSet and stream not in childrenSet:
                        if includeWorkspaces or streamMap[stream].Type.lower() != "workspace":
                            if ignoreTimelocks or streamMap[stream].time is None or streamMap[stream].time >= transaction.time:
                                if doDiffs and transaction.id > 1:
                                    diffResult = diff(all=True, informationOnly=True, verSpec1=stream, verSpec2=stream, transactionRange="{0}-{1}".format(transaction.id, transaction.id - 1), useCache=useCache)
                                    if len(diffResult.elements) != 0:
                                        newChildrenSet.add(stream)
                                else:
                                    newChildrenSet.add(stream)
            
            rv = []
            for stream in childrenSet:
                rv.append(streamMap[stream])
            
        return rv

# ################################################################################################ #
# Script Main                                                                                      #
# ################################################################################################ #
import sys
import argparse

def clDeepHist(args):
    transactions = ext.deep_hist(depot=args.depot, stream=args.stream, timeSpec=args.timeSpec, ignoreTimelocks=args.ignoreTimelocks, useCache=(args.cacheFile is not None))
    if transactions is not None and len(transactions) > 0:
        print("tr. type; destination stream; tr. number; username;")
        for tr in transactions:
            print("{Type}; {stream}; {id}; {user};".format(id=tr.id, user=tr.user, Type=tr.Type, stream=tr.affectedStream()[0]))
        return 0
    else:
        print("No affected streams")
        return 1

def clAffectedStreams(args):
    streams = ext.affected_streams(depot=args.depot, transaction=args.transaction, includeWorkspaces=args.includeWorkspaces, ignoreTimelocks=args.ignoreTimelocks, doDiffs=args.diffCheck, useCache=(args.cacheFile is not None))
    if streams is not None and len(streams) > 0:
        print("stream name; stream id; stream type;")
        for s in streams:
            print("{streamName}; {streamId}; {Type};".format(streamName=s.name, streamId=s.streamNumber, Type=s.Type))
        return 0
    else:
        print("No affected streams")
        return 1

def clGetMkstreamTransaction(args):
    mkstreamTr = ext.get_mkstream_transaction(stream=args.stream, depot=args.depot, useCache=(args.cacheFile is not None))
    if mkstreamTr is not None:
        print("tr. type; destination stream; tr. number; username;")
        print("{Type}; {stream}; {id}; {user};".format(id=mkstreamTr.id, user=mkstreamTr.user, Type=mkstreamTr.Type, stream=mkstreamTr.affectedStream()[0]))
        return 0
    else:
        print("No mkstream transaction")
        return 1

if __name__ == "__main__":
    # Define the argument parser
    argparser = argparse.ArgumentParser(description='Custom extensions to the main accurev command line tool.')

    subparsers = argparser.add_subparsers(title='commands')

    # deep hist subcommand
    deepHistParser = subparsers.add_parser('deep-hist', help='Shows all the transactions that could have affected the current stream.')
    deepHistParser.description = 'Shows all the transactions that could have affected the current stream.'
    deepHistParser.add_argument('-p', '--depot',     dest='depot',    help='The name of the depot in which the transaction occurred')
    deepHistParser.add_argument('-s', '--stream',    dest='stream',   help='The accurev stream for which we want to know all the transactions which could have affected it.')
    deepHistParser.add_argument('-t', '--time-spec', dest='timeSpec', required=True, help='The accurev time-spec. e.g. 17-21 or 99.')
    deepHistParser.add_argument('-i', '--ignore-timelocks', dest='ignoreTimelocks', action='store_true', default=False, help='The returned set of transactions will include transactions which occurred in the parent stream before the timelock of the child stream (if any).')
    deepHistParser.add_argument('-c', '--cache', dest='cacheFile', help='Specifies the command cacne filename to use for caching of accurev commands.')

    deepHistParser.set_defaults(func=clDeepHist)


    # deep hist subcommand
    affectedStreamsParser = subparsers.add_parser('affected-streams', help='Shows all the transactions that could have affected the current stream.')
    affectedStreamsParser.description = 'Shows all the transactions that could have affected the current stream.'
    affectedStreamsParser.add_argument('-p', '--depot',     dest='depot',    required=True, help='The name of the depot in which the transaction occurred')
    affectedStreamsParser.add_argument('-t', '--transaction', dest='transaction', required=True, help='The accurev transaction number for which we want to know the affected streams.')
    affectedStreamsParser.add_argument('-w', '--include-workspaces', dest='includeWorkspaces', action='store_true', default=False, help='The returned set of streams will include workspaces if this option is specified.')
    affectedStreamsParser.add_argument('-i', '--ignore-timelocks', dest='ignoreTimelocks', action='store_true', default=False, help='The returned set of streams will include streams whose timelocks would have otherwise prevented this stream from affecting them.')
    affectedStreamsParser.add_argument('-d', '--diff-check', dest='diffCheck', action='store_true', default=False, help='The returned set of streams will not include streams whose diffs to previous transaction return empty.')
    affectedStreamsParser.add_argument('-c', '--cache', dest='cacheFile', help='Specifies the command cacne filename to use for caching of accurev commands.')

    affectedStreamsParser.set_defaults(func=clAffectedStreams)

    # find mkstream subcommand
    findMkstreamParser = subparsers.add_parser('find-mkstream', help='Finds the mkstream transaction for the requested stream.')
    findMkstreamParser.description = 'Finds the mkstream transaction for the requested stream which may be non-trivial for old depots that have undergone a number of accurev version updates.'
    findMkstreamParser.add_argument('-p', '--depot',  dest='depot',    help='The name of the depot in which the stream was created (optional).')
    findMkstreamParser.add_argument('-s', '--stream', dest='stream',   required=True, help='The name or number of the stream for which we wish to find the mkstream transaction.')
    findMkstreamParser.add_argument('-c', '--cache', dest='cacheFile', help='Specifies the command cacne filename to use for caching of accurev commands.')

    findMkstreamParser.set_defaults(func=clGetMkstreamTransaction)

    # Parse the arguments and execute
    args = argparser.parse_args()

    if args.cacheFile is not None:
        ext.enable_command_cache(args.cacheFile)

    rv = args.func(args)

    if args.cacheFile is not None:
        ext.disable_command_cache()

    if rv != 0:
        sys.exit(rv)

