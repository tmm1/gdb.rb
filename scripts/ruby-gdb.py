import re
import gdb
import time
import os

class ZeroDict(dict):
  def __getitem__(self, i):
    if i not in self: self[i] = 0
    return dict.__getitem__(self, i)

class ListDict(dict):
  def __getitem__(self, i):
    if i not in self: self[i] = []
    return dict.__getitem__(self, i)

class Ruby (gdb.Command):
  def __init__ (self):
    super (Ruby, self).__init__ ("ruby", gdb.COMMAND_NONE, gdb.COMPLETE_COMMAND, True)

class RubyThreads (gdb.Command):
  def __init__ (self):
    super (RubyThreads, self).__init__ ("ruby threads", gdb.COMMAND_NONE)

  def complete (self, text, word):
    if text == word:
      if word == '':
        return ['trace', 'list']
      elif word[0] == 't':
        return ['trace']
      elif word[0] == 'l':
        return ['list']

  def invoke (self, arg, from_tty):
    self.dont_repeat()
    if re.match('trace', arg):
      self.trace()
    else:
      self.type = arg == 'list' and arg or None
      self.show()

  def trace (self):
    self.type = 'list'
    self.curr = None
    self.main = gdb.parse_and_eval('rb_main_thread')

    self.unwind = gdb.parameter('unwindonsignal')
    gdb.execute('set unwindonsignal on')

    gdb.execute('watch rb_curr_thread')
    gdb.breakpoints()[-1].silent = True
    num = gdb.breakpoints()[-1].number

    try:
      prev = None
      while True:
        gdb.execute('continue')
        curr = gdb.parse_and_eval('rb_curr_thread')
        if curr == prev: break
        self.print_thread(curr)
        prev = curr
    except KeyboardInterrupt:
      None

    gdb.execute('delete %d' % num)
    gdb.execute('set unwindonsignal %s' % (self.unwind and 'on' or 'off'))

  def show (self):
    self.main = gdb.parse_and_eval('rb_main_thread')
    self.curr = gdb.parse_and_eval('rb_curr_thread')
    self.now = time.time()

    try:
      gdb.parse_and_eval('rb_thread_start_2')
    except RuntimeError:
      self.is_heap_stack = False
    else:
      self.is_heap_stack = True

    if self.main == 0:
      print "Ruby VM is not running!"
    else:
      th = self.main
      while True:
        self.print_thread(th)
        th = th['next']
        if th == self.main: break

      print

  def print_thread (self, th):
    if self.type != 'list': print
    print th,
    print th == self.main and 'main' or '    ',
    print th == self.curr and 'curr' or '    ',
    print "thread", " %s" % str(th['status']).ljust(16), "%s" % self.wait_state(th), "   ",
    if th != self.curr:
      print "% 8d bytes" % th['stk_len']
    else:
      print

    if self.type == 'list': return

    if th == self.curr:
      frame = gdb.parse_and_eval('ruby_frame')
      node = gdb.parse_and_eval('ruby_current_node')
    else:
      frame = th['frame']
      node = frame['node']

    self.print_stack(th, frame, node)

  def wait_state (self, th):
    mask = th['wait_for']
    state = list()
    if mask == 0: state.append('WAIT_NONE')
    if mask & 1:  state.append('WAIT_FD(%d)' % th['fd'])
    if mask & 2:  state.append('WAIT_SELECT')
    if mask & 4:
      delay = th['delay']
      time = delay-self.now
      state.append('WAIT_TIME(%5.2f)' % time)
    if mask & 8:  state.append('WAIT_JOIN(%s)' % th['join'])
    if mask & 16: state.append('WAIT_PID')
    return ', '.join(state).ljust(22)

  def print_stack (self, th, frame, node):
    while True:
      stk_pos = th['stk_pos']
      stk_ptr = th['stk_ptr']
      stk_len = th['stk_len']
      addr = gdb.parse_and_eval('(VALUE*)%s' % frame)

      if not self.is_heap_stack and th != self.curr and stk_pos < addr and addr < (stk_pos+stk_len):
        frame = (addr-stk_pos) + stk_ptr
        frame = gdb.parse_and_eval('(struct FRAME *)%s' % frame)
        node = frame['node']

      file = node['nd_file'].string()
      line = gdb.parse_and_eval('nd_line(%s)' % node)
      type = gdb.parse_and_eval('(enum node_type) nd_type(%s)' % node)

      if frame['last_func']:
        try:
          method = gdb.parse_and_eval('rb_id2name(%s)' % frame['last_func']).string()
        except:
          method = '(unknown)'
      else:
        method = '(unknown)'

      print "  ",
      print str(type).lower().center(18), "%s in %s:%d" % (method, file, line)

      if frame['prev'] == 0 or frame['last_func'] == 0: break
      frame = frame['prev']
      node = frame['node']
      if node == 0: break

class RubyTrace (gdb.Command):
  def __init__ (self):
    super (RubyTrace, self).__init__ ("ruby trace", gdb.COMMAND_NONE, gdb.COMPLETE_NONE)

  def setup (self):
    commands = """
      set $func = malloc(1)
      p ((char*)$func)[0] = '\xc3'
      p mprotect(($func&0xfffffffffffff000), 1, 0x7)
      p rb_add_event_hook($func, RUBY_EVENT_C_CALL|RUBY_EVENT_CALL)
      b *$func
    """.split("\n")

    for c in commands:
      gdb.execute(c)

    gdb.breakpoints()[-1].silent = True
    self.func = gdb.parse_and_eval('$func')

    self.unwind = gdb.parameter('unwindonsignal')
    gdb.execute('set unwindonsignal on')

  def teardown (self):
    commands = """
      finish
      clear *$func
      p mprotect(($func&0xfffffffffffff000), 1, 0x3)
      p rb_remove_event_hook($func)
      p free($func)
      set $func = 0
    """.split("\n")

    for c in commands:
      gdb.execute(c)

    gdb.execute('set unwindonsignal %s' % (self.unwind and 'on' or 'off'))

  def invoke (self, arg, from_tty):
    self.dont_repeat()
    num = arg and int(arg) or 100
    self.setup()

    try:
      while num > 0:
        num -= 1
        gdb.execute('continue')

        frame = gdb.selected_frame()
        if frame.pc() != self.func:
          raise KeyboardInterrupt

        node = gdb.parse_and_eval('(NODE*) $rsi')
        file = node['nd_file'].string()
        line = gdb.parse_and_eval('nd_line(%s)' % node)
        method = gdb.parse_and_eval('rb_id2name($rcx)')
        method = method > 0 and method.string() or '(unknown)'

        print "%s in %s:%d" % (method,file,line)

      self.teardown()
    except KeyboardInterrupt:
      self.teardown()
    except RuntimeError, text:
      self.teardown()
      if not re.search('signaled while in a function called from GDB', text):
        raise

class RubyObjects (gdb.Command):
  def __init__ (self):
    super (RubyObjects, self).__init__ ("ruby objects", gdb.COMMAND_NONE)

  def invoke (self, arg, from_tty):
    self.dont_repeat()
    if arg == 'classes':
      self.print_classes()
    elif arg == 'nodes':
      self.print_nodes()
    elif Ruby.is_18 and arg == 'strings':
      self.print_strings()
    elif Ruby.is_18 and arg == 'hashes':
      self.print_hashes()
    elif Ruby.is_18 and arg == 'arrays':
      self.print_arrays()
    else:
      self.print_stats()

  def complete (self, text, word):
    if text == word:
      if word == '':
        if Ruby.is_18:
          return ['classes', 'nodes', 'strings', 'hashes', 'arrays']
        else:
          return ['classes', 'nodes']
      elif word[0] == 'c':
        return ['classes']
      elif word[0] == 'n':
        return ['nodes']
      elif Ruby.is_18 and word[0] == 's':
        return ['strings']
      elif Ruby.is_18 and word[0] == 'h':
        return ['hashes']
      elif Ruby.is_18 and word[0] == 'a':
        return ['arrays']

  def print_nodes (self):
    nodes = ZeroDict()

    for (obj, type) in self.live_objects():
      if type == RubyObjects.ITYPES['node']:
        if Ruby.is_18:
          # for performance only, the 1.9 path below will work as well
          # but requires a call to gdb.parse_and_eval
          type = (int(obj['as']['node']['flags']) >> 12) & 0xff
        else:
          type = int(gdb.parse_and_eval('nd_type(%s)' % obj))
        nodes[ type ] += 1

    for (node, num) in sorted(nodes.items(), key=lambda(k,v):(v,k)):
      print "% 8d %s" % (num, gdb.parse_and_eval('(enum node_type) (%d)' % node))

  def print_classes (self):
    classes = ZeroDict()

    for (obj, type) in self.live_objects():
      if type == 0x0:
        pass # none
      elif type == 0x3b:
        pass # blktag
      elif type == 0x3c:
        pass # undef
      elif type == 0x3d:
        pass # varmap
      elif type == 0x3e:
        pass # scope
      elif type == 0x3f:
        pass # node
      else:
        klass = obj['as']['basic']['klass']
        if klass:
          classes[ int(klass) ] += 1

    for (klass, num) in sorted(classes.items(), key=lambda(k,v):(v,k)):
      print "% 8d %s" % (num, gdb.parse_and_eval('rb_class2name(%d)' % klass).string())

  def print_strings (self):
    strings = ZeroDict()
    bytes = 0

    for (obj, type) in self.live_objects():
      if type == RubyObjects.ITYPES['string']:
        s = obj['as']['string']
        ptr = s['ptr']
        if ptr:
          bytes += s['len']
          try:
            strings[ ptr.string() ] += 1
          except:
            None

    for (s, num) in sorted(strings.items(), key=lambda(k,v):(v,k)):
      print "% 9d" % num, repr(s)

    print
    print "% 9d" % len(strings), "unique strings"
    print "% 9d" % bytes, "bytes"
    print

  def print_hashes (self):
    sample = ListDict()
    hash_sizes = ZeroDict()
    num_elems = 0

    for (obj, type) in self.live_objects():
      if type == 0xb:
        h = obj['as']['hash']
        tbl = h['tbl']
        l = int(tbl['num_entries'])

        num_elems += l
        hash_sizes[l] += 1
        if len(sample[l]) < 5: sample[l].append(h.address)

    print " elements instances"
    for (l, num) in sorted(hash_sizes.items()):
      print "%9d" % l, num, "(", ', '.join([ str(i) for i in sample[l] ]), ")"

    print
    print "% 9d" % sum(hash_sizes.values()), "hashes"
    print "% 9d" % num_elems, "member elements"
    print

  def print_arrays (self):
    sample = ListDict()
    array_sizes = ZeroDict()
    num_elems = 0

    for (obj, type) in self.live_objects():
      if type == 0x9:
        a = obj['as']['array']
        l = int(a['len'])

        num_elems += l
        array_sizes[l] += 1
        if len(sample[l]) < 5: sample[l].append(a.address)

    print " elements instances"
    for (l, num) in sorted(array_sizes.items()):
      print "%9d" % l, num, "(", ', '.join([ str(i) for i in sample[l] ]), ")"

    print
    print "% 9d" % sum(array_sizes.values()), "arrays"
    print "% 9d" % num_elems, "member elements"
    print

  def print_stats (self):
    total = live = free = 0
    types = ZeroDict()

    for (obj, flags) in self.all_objects():
      if flags:
        live += 1
        types[ int(flags & RubyObjects.T_MASK) ] += 1
      else:
        free += 1

      total += 1

    print
    print "  HEAPS    % 9d" % self.heaps_used
    print "  SLOTS    % 9d" % total
    print "  LIVE     % 9d (%3.2f%%)" % (live, 100.0*live/total)
    print "  FREE     % 9d (%3.2f%%)" % (free, 100.0*free/total)
    print

    for (type, num) in sorted(types.items(), key=lambda(k,v):(v,k)):
      print "  %s % 9d (%3.2f%%)" % (self.obj_type(type).ljust(8), num, 100.0*num/live)

    print

  def all_objects (self):
    self.heaps_used = gdb.parse_and_eval('heaps_used')

    for i in xrange(self.heaps_used):
      p = gdb.parse_and_eval("(RVALUE*) heaps[%i].slot" % i)
      pend = p + gdb.parse_and_eval("heaps[%i].limit" % i)

      while p < pend:
        yield p, p['as']['basic']['flags']
        p += 1

  def live_objects (self):
    for (obj, flags) in self.all_objects():
      if flags:
        yield obj, int(flags & RubyObjects.T_MASK)

  def obj_type (self, type):
    return RubyObjects.TYPES.get(type, 'unknown')

class RubyMethodCache (gdb.Command):
  def __init__ (self):
    super (RubyMethodCache, self).__init__ ("ruby methodcache", gdb.COMMAND_NONE)

  def invoke (self, arg, from_tty):
    self.dont_repeat()
    cache = gdb.parse_and_eval('cache')
    size = 0x800
    empty = 0

    for i in xrange(size):
      entry = cache[i]
      if entry['mid'] != 0:
        klass = gdb.parse_and_eval('rb_class2name(%d)' % entry['klass'])
        method = gdb.parse_and_eval('rb_id2name(%d)' % entry['mid'])
        print " %s#%s" % (klass and klass.string() or '(unknown)',  method and method.string() or '(unknown)')
      else:
        empty += 1

    print
    print "%d empty slots (%.2f%%)" % (empty, empty*100.0/size)
    print

class RubyPrint (gdb.Command):
  def __init__ (self):
    super (RubyPrint, self).__init__ ("ruby print", gdb.COMMAND_NONE)

  def invoke (self, arg, from_tty):
    self.dont_repeat()

    type = int(gdb.parse_and_eval("((struct RBasic *)(%d))->flags & 0x3f" % int(arg,0)))
    rtype = RubyObjects.TYPES.get(type, 'unknown')

    if rtype == 'array':
      print rtype
    elif rtype == 'hash':
      print rtype
    else:
      print 'unknown'

class RubyEval (gdb.Command):
  def __init__ (self):
    super (RubyEval, self).__init__ ("ruby eval", gdb.COMMAND_NONE)

  def invoke (self, arg, from_tty):
    self.dont_repeat()
    arg = arg.replace('\\', '\\\\').replace('"', '\\\"')
    print gdb.parse_and_eval("RSTRING_PTR(rb_eval_string_protect(\"begin; (%s).inspect; rescue Exception => e; e.inspect; end\", 0))" % arg).string()


##
# Create common GDB commands

Ruby()
RubyEval()
RubyObjects()

##
# Detect ruby version

ruby = gdb.execute("info files", to_string=True).split("\n")[0]
ruby = re.search('"(.+)"\.?$', ruby)
ruby = ruby.group(1)
ruby = os.popen("%s -v" % ruby).read()

##
# Common macros for 1.8 and 1.9

macros = """
  #define R_CAST(st)   (struct st*)
  #define RBASIC(obj)  (R_CAST(RBasic)(obj))
  #define RSTRING(obj) (R_CAST(RString)(obj))
  #define RNODE(obj)  (R_CAST(RNode)(obj))
"""

##
# Constants

Ruby.is_18  = False
Ruby.is_19  = False
Ruby.is_ree = False

##
# Version specific macros and commands

if re.search('1\.9\.\d', ruby):
  Ruby.is_19 = True
  RubyObjects.T_MASK = 0x1f

  ##
  # Common 1.9 macros
  macros += """
    #define NODE_TYPESHIFT 8
    #define NODE_TYPEMASK  (((VALUE)0x7f)<<NODE_TYPESHIFT)
    #define nd_type(n) ((int) (((RNODE(n))->flags & NODE_TYPEMASK)>>NODE_TYPESHIFT))

    #define RSTRING_PTR(str) (!(RBASIC(str)->flags & RSTRING_NOEMBED) ? RSTRING(str)->as.ary : RSTRING(str)->as.heap.ptr)
    #define RSTRING_NOEMBED FL_USER1
    #define FL_USER1     (((VALUE)1)<<(FL_USHIFT+1))
    #define FL_USHIFT    12

    #define GET_VM() ruby_current_vm
    #define rb_objspace (*GET_VM()->objspace)
    #define objspace rb_objspace

    #define heaps     objspace->heap.ptr
    #define heaps_length    objspace->heap.length
    #define heaps_used    objspace->heap.used
  """

else:
  Ruby.is_18 = True
  RubyObjects.T_MASK = 0x3f

  ##
  # 1.8 specific ruby commands
  RubyThreads()
  RubyTrace()
  RubyMethodCache()
  RubyPrint()

  ##
  # Detect REE vs MRI
  if re.search('Enterprise', ruby):
    Ruby.is_ree = True
    macros += """
      #define FL_USHIFT   12
    """
  else:
    macros += """
      #define FL_USHIFT   11
    """

  ##
  # Common 1.8 macros
  macros += """
    #define RSTRING_PTR(obj) (RSTRING(obj)->ptr)
    #define CHAR_BIT 8
    #define NODE_LSHIFT (FL_USHIFT+8)
    #define NODE_LMASK  (((long)1<<(sizeof(NODE*)*CHAR_BIT-NODE_LSHIFT))-1)
    #define nd_line(n) ((unsigned int)(((RNODE(n))->flags>>NODE_LSHIFT)&NODE_LMASK))
    #define nd_type(n) ((int)(((RNODE(n))->flags>>FL_USHIFT)&0xff))

    #define T_MASK   0x3f
    #define BUILTIN_TYPE(x) (((struct RBasic*)(x))->flags & T_MASK)

    #define WAIT_FD (1<<0)
    #define WAIT_SELECT (1<<1)
    #define WAIT_TIME (1<<2)
    #define WAIT_JOIN (1<<3)
    #define WAIT_PID (1<<4)

    #define RUBY_EVENT_CALL     0x08
    #define RUBY_EVENT_C_CALL   0x20
  """

##
# Execute macro definitions

for m in macros.split("\n"):
  if len(m.strip()) > 0:
    gdb.execute(m.replace('#', 'macro ', 1))

##
# Define types

RubyObjects.TYPES = {}

if Ruby.is_19:
  for t in gdb.lookup_type('enum ruby_value_type').fields():
    name = t.name
    val  = int(gdb.parse_and_eval(name))
    gdb.execute("macro define %s %s" % (name[5:], val))
    RubyObjects.TYPES[val] = name[7:].lower()
else:
  types = """
    T_NONE   0x00

    T_NIL    0x01
    T_OBJECT 0x02
    T_CLASS  0x03
    T_ICLASS 0x04
    T_MODULE 0x05
    T_FLOAT  0x06
    T_STRING 0x07
    T_REGEXP 0x08
    T_ARRAY  0x09
    T_FIXNUM 0x0a
    T_HASH   0x0b
    T_STRUCT 0x0c
    T_BIGNUM 0x0d
    T_FILE   0x0e

    T_TRUE   0x20
    T_FALSE  0x21
    T_DATA   0x22
    T_MATCH  0x23
    T_SYMBOL 0x24

    T_BLKTAG 0x3b
    T_UNDEF  0x3c
    T_VARMAP 0x3d
    T_SCOPE  0x3e
    T_NODE   0x3f
  """.split("\n")

  for t in types:
    if len(t.strip()) > 0:
      name, val = t.split()
      gdb.execute("macro define %s %s" % (name, val))
      RubyObjects.TYPES[int(val,16)] = name[2:].lower()

RubyObjects.ITYPES = dict([[v,k] for k,v in RubyObjects.TYPES.items()])

##
# Set GDB options

settings = """
  set height 0
  set width 0
  set print pretty

  set history save on
  set history filename ~/.gdbrb_history

  set debug-file-directory /usr/lib/debug
""".split("\n")

for s in settings:
  if len(s.strip()) > 0:
    gdb.execute(s)
