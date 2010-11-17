spec = Gem::Specification.new do |s|
  s.name = 'gdb.rb'
  s.version = '0.1.6'
  s.date = '2010-11-16'
  s.rubyforge_project = 'gdb-rb'
  s.summary = 'gdb hooks for MRI/REE and YARV'
  s.description = 'A set of gdb7 extensions for the MRI/REE 1.8.x interpreter (and basic support for YARV 1.9.2)'

  s.homepage = "http://github.com/tmm1/gdb.rb"

  s.authors = ["Aman Gupta"]
  s.email = "gdb@tmm1.net"

  s.has_rdoc = false
  s.extensions = 'ext/extconf.rb'
  s.bindir = 'bin'
  s.executables << 'gdb.rb'

  s.files = `git ls-files`.split("\n").sort
end
