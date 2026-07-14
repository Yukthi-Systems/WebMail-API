# ACL (Access Control List)

## Overview

Letter | Permission Name | What It Allows
-------|----------------|----------------
l | Lookup | See folder
r | Read | Read mails
s | Seen state | Mark as seen/unseen
w | Write flags | Mark read/starred/etc.
i | Insert | Add new emails
p | Post | Deliver to folder
k | Create folders | Create subfolders
x | Delete folders | Delete subfolders
t | Delete mails | Move to Trash
e | Expunge mails | Permanently delete
a | Administer | Change ACLs


## Permissions and their meanings

Right | Meaning
-----|--------
l | lookup (can see the folder exists)
r | read messages
s | keep seen/unseen state
w | write flags (e.g., mark read, star/unstar)
i | insert (append new messages)
p | post (send mail to folder, like shared mailboxes)
k | create subfolders
x | delete subfolders
t | delete messages
e | expunge (permanently remove deleted mails)
a | administer (set ACLs for others)
