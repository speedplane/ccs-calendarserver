##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Directory service implementation for users who are allowed to authorize
as other principals.
"""

__all__ = [
    "WikiDirectoryService",
]

from twisted.python.filepath import FilePath
from twisted.web2.dav import davxml
from twisted.web.xmlrpc import Proxy, Fault
from twisted.web2.http import HTTPError, StatusResponse
from twisted.web2.auth.wrapper import UnauthorizedResponse

from twisted.internet.defer import inlineCallbacks, returnValue


from twisted.web2.dav.resource import TwistedACLInheritable
from twistedcaldav.config import config
from twistedcaldav.py.plistlib import readPlist
from twistedcaldav.directory.directory import (DirectoryService,
                                               DirectoryRecord,
                                               UnknownRecordTypeError)
from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource
from twistedcaldav.log import Logger

log = Logger()

class WikiDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation for Wikis.
    """
    baseGUID = "d79ef1e0-9a42-11dd-ad8b-0800200c9a66"

    realmName = "Wiki"

    recordType_wikis = "wikis"


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.realmName)

    def __init__(self):
        super(WikiDirectoryService, self).__init__()
        self.byGUID = {}
        self.byShortName = {}

    def recordTypes(self):
        return (WikiDirectoryService.recordType_wikis,)

    def listRecords(self, recordType):
        return []

    def recordWithShortName(self, recordType, shortName):
        if recordType != WikiDirectoryService.recordType_wikis:
            raise UnknownRecordTypeError(recordType)

        if self.byShortName.has_key(shortName):
            return self.byShortName[shortName]

        record = WikiDirectoryRecord(
            self,
            WikiDirectoryService.recordType_wikis,
            shortName,
            None
        )
        self.log_info("Returning wiki record with GUID %s" % (record.guid,))
        self.byGUID[record.guid] = record
        self.byShortName[shortName] = record
        return record

    def recordWithGUID(self, guid):
        return self.byGUID.get(guid, None)



class WikiDirectoryRecord(DirectoryRecord):
    """
    L{DirectoryRecord} implementation for Wikis.
    """

    def __init__(self, service, recordType, shortName, entry):
        super(WikiDirectoryRecord, self).__init__(
            service=service,
            recordType=recordType,
            guid=None,
            shortName=shortName,
            fullName=shortName,
            firstName="",
            lastName="",
            emailAddresses=set(),
            calendarUserAddresses=set(),
            autoSchedule=False,
            enabledForCalendaring=True)



@inlineCallbacks
def getWikiACL(request, wikiID):

    wikiConfig = config.Authentication["Wiki"]

    userID = "unauthenticated"

    try:
        url = str(request.authzUser.children[0])
        principal = (yield request.locateResource(url))
        # TODO: Fix the circular dependency between wiki.py and calendar.py
        if isinstance(principal, DirectoryCalendarPrincipalResource):
            userID = principal.record.guid
    except:
        # TODO: better error handling
        pass

    proxy = Proxy(wikiConfig["URL"])
    try:

        access = (yield proxy.callRemote(wikiConfig["WikiMethod"],
            userID, wikiID))

        log.info("getWikiACL: user [%s], wiki [%s], access [%s]" % (userID,
            wikiID, access))

        if access == "read":
            returnValue(
                davxml.ACL(
                    davxml.ACE(
                        request.authnUser,
                        davxml.Grant(
                            davxml.Privilege(davxml.Read()),
                        ),
                        TwistedACLInheritable(),
                    )
                )
            )

        elif access in ("write", "admin"):
            returnValue(
                davxml.ACL(
                    davxml.ACE(
                        request.authnUser,
                        davxml.Grant(
                            davxml.Privilege(davxml.Read()),
                        ),
                        TwistedACLInheritable(),
                    ),
                    davxml.ACE(
                        request.authnUser,
                        davxml.Grant(
                            davxml.Privilege(davxml.Write()),
                        ),
                        TwistedACLInheritable(),
                    )
                )
            )

        else: # "no-access":

            if userID == "unauthenticated":
                # Return a 401 so they have an opportunity to log in
                raise HTTPError(
                    UnauthorizedResponse(
                        request.credentialFactories,
                        request.remoteAddr
                    )
                )

            raise HTTPError(
                StatusResponse(
                    403,
                    "You are not allowed to access this wiki"
                )
            )

    except Fault, fault:

        log.info("getWikiACL: user [%s], wiki [%s], FAULT [%s]" % (userID,
            wikiID, fault))

        if fault.faultCode == 2: # non-existent user
            raise HTTPError(StatusResponse(403, fault.faultString))

        else: # fault.faultCode == 12, non-existent wiki
            raise HTTPError(StatusResponse(404, fault.faultString))

