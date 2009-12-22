spec = Gem::Specification.new do |s|
  s.name = 'gdb.rb'
  s.version = '0.1.3'
  s.date = '2009-12-22'
  s.rubyforge_project = 'gdb-rb'
  s.summary = 'gdb hooks for MRI'
  s.description = 'A set of gdb7 extensions for the MRI interpreter'

  s.homepage = "http://github.com/tmm1/gdb.rb"

  s.authors = ["Aman Gupta"]
  s.email = "gdb@tmm1.net"

  s.has_rdoc = false
  s.extensions = 'ext/extconf.rb'
  s.bindir = 'bin'
  s.executables << 'gdb.rb'

  # ruby -rpp -e' pp `git ls-files`.split("\n").sort '
  s.files = %w[
    README
    bin/gdb.rb
    ext/Makefile
    ext/extconf.rb
    ext/src/gdb-7.0.tar.bz2
    gdb.rb.gemspec
    patches/gdb-breakpoints.patch
    patches/gdb-eval.patch
    patches/gdb-leak.patch
    patches/gdb-strings.patch
    scripts/ruby-gdb.py
  ]
end
