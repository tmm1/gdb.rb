import re
import gdb
import time

class ZeroDict(dict):
  def __getitem__(self, i):
    if i not in self: self[i] = 0
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
    if re.match('trace', arg):
      self.trace()
    else:
      self.type = arg == 'list' and arg or None
      self.show()

  def trace (self):
    self.type = 'list'
    self.curr = None
    self.main = gdb.eval('rb_main_thread')

    self.unwind = gdb.parameter('unwindonsignal')
    gdb.execute('set unwindonsignal on')

    gdb.execute('watch rb_curr_thread')
    gdb.breakpoints()[-1].silent = True
    num = gdb.breakpoints()[-1].number

    try:
      prev = None
      while True:
        gdb.execute('continue')
        curr = gdb.eval('rb_curr_thread')
        if curr == prev: break
        self.print_thread(curr)
        prev = curr
    except KeyboardInterrupt:
      None

    gdb.execute('delete %d' % num)
    gdb.execute('set unwindonsignal %s' % (self.unwind and 'on' or 'off'))

  def show (self):
    self.main = gdb.eval('rb_main_thread')
    self.curr = gdb.eval('rb_curr_thread')
    self.now = time.time()

    try:
      gdb.eval('rb_thread_start_2')
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
      frame = gdb.eval('ruby_frame')
      node = gdb.eval('ruby_current_node')
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
      addr = gdb.eval('(VALUE*)%s' % frame)

      if not self.is_heap_stack and th != self.curr and stk_pos < addr and addr < (stk_pos+stk_len):
        frame = (addr-stk_pos) + stk_ptr
        frame = gdb.eval('(struct FRAME *)%s' % frame)
        node = frame['node']

      file = node['nd_file'].string()
      line = gdb.eval('nd_line(%s)' % node)
      type = gdb.eval('(enum node_type) nd_type(%s)' % node)

      if frame['last_func']:
        try:
          method = gdb.eval('rb_id2name(%s)' % frame['last_func']).string()
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
    self.func = gdb.eval('$func')

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

        node = gdb.eval('(NODE*) $rsi')
        file = node['nd_file'].string()
        line = gdb.eval('nd_line(%s)' % node)
        method = gdb.eval('rb_id2name($rcx)')
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
    if arg == 'classes':
      self.print_classes()
    elif arg == 'nodes':
      self.print_nodes()
    elif arg == 'strings':
      self.print_strings()
    else:
      self.print_stats()

  def complete (self, text, word):
    if text == word:
      if word == '':
        return ['classes', 'strings', 'nodes']
      elif word[0] == 'c':
        return ['classes']
      elif word[0] == 'n':
        return ['nodes']
      elif word[0] == 's':
        return ['strings']

  def print_nodes (self):
    nodes = ZeroDict()

    for (obj, type) in self.live_objects():
      if type == 0x3f:
        nodes[ (int(obj['as']['node']['flags']) >> 12) & 0xff ] += 1

    for (node, num) in sorted(nodes.items(), key=lambda(k,v):(v,k)):
      print "% 8d %s" % (num, gdb.eval('(enum node_type) (%d)' % node))

  def print_classes (self):
    classes = ZeroDict()

    for (obj, type) in self.live_objects():
      if type == 0x2:
        classes[ int(obj['as']['basic']['klass']) ] += 1

    for (klass, num) in sorted(classes.items(), key=lambda(k,v):(v,k)):
      print "% 8d %s" % (num, gdb.eval('rb_class2name(%d)' % klass).string())

  def print_strings (self):
    strings = ZeroDict()
    bytes = 0

    for (obj, type) in self.live_objects():
      if type == 0x7:
        s = obj['as']['string']
        ptr = s['ptr']
        if ptr:
          bytes += s['len']
          strings[ ptr.string() ] += 1

    for (s, num) in sorted(strings.items(), key=lambda(k,v):(v,k)):
      print "% 9d" % num, repr(s)

    print
    print "% 9d" % len(strings), "unique strings"
    print "% 9d" % bytes, "bytes"
    print

  def print_stats (self):
    total = live = free = 0
    types = ZeroDict()

    for (obj, flags) in self.all_objects():
      if flags:
        live += 1
        types[ int(flags & 0x3f) ] += 1
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
    self.heaps_used = gdb.eval('heaps_used')

    for i in xrange(self.heaps_used):
      p = gdb.eval("(RVALUE*) heaps[%i].slot" % i)
      pend = p + gdb.eval("heaps[%i].limit" % i)

      while p < pend:
        yield p, p['as']['basic']['flags']
        p += 1

  def live_objects (self):
    for (obj, flags) in self.all_objects():
      if flags:
        yield obj, int(flags & 0x3f)

  def obj_type (self, type):
    return RubyObjects.TYPES.get(type, 'unknown')

Ruby()
RubyThreads()
RubyTrace()
RubyObjects()

macros = """
  macro define R_CAST(st)   (struct st*)
  macro define RNODE(obj)  (R_CAST(RNode)(obj))
  macro define FL_USHIFT    12
  macro define CHAR_BIT 8
  macro define NODE_LSHIFT (FL_USHIFT+8)
  macro define NODE_LMASK  (((long)1<<(sizeof(NODE*)*CHAR_BIT-NODE_LSHIFT))-1)
  macro define nd_line(n) ((unsigned int)(((RNODE(n))->flags>>NODE_LSHIFT)&NODE_LMASK))
  macro define nd_type(n) ((int)(((RNODE(n))->flags>>FL_USHIFT)&0xff))

  macro define T_MASK   0x3f
  macro define BUILTIN_TYPE(x) (((struct RBasic*)(x))->flags & T_MASK)

  macro define WAIT_FD (1<<0)
  macro define WAIT_SELECT (1<<1)
  macro define WAIT_TIME (1<<2)
  macro define WAIT_JOIN (1<<3)
  macro define WAIT_PID (1<<4)

  macro define RUBY_EVENT_CALL     0x08
  macro define RUBY_EVENT_C_CALL   0x20
""".split("\n")

for m in macros:
  if len(m.strip()) > 0:
    gdb.execute(m)

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

RubyObjects.TYPES = {}

for t in types:
  if len(t.strip()) > 0:
    name, val = t.split()
    gdb.execute("macro define %s %s" % (name, val))
    RubyObjects.TYPES[int(val,16)] = name[2:].lower()

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
