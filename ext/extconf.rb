CWD = File.expand_path(File.dirname(__FILE__))

def sys(cmd)
  puts "  -- #{cmd}"
  unless ret = xsystem(cmd)
    raise "#{cmd} failed, please report to gdb@tmm1.net with pastie.org link to #{CWD}/mkmf.log and #{CWD}/src/gdb-7.0/config.log"
  end
  ret
end

require 'mkmf'
require 'fileutils'

if RUBY_VERSION >= "1.9"
  STDERR.puts "\n\n"
  STDERR.puts "***************************************************************************************"
  STDERR.puts "************************** ruby 1.9 is not supported (yet) =( *************************"
  STDERR.puts "***************************************************************************************"
  exit(1)
end

if `uname -a 2>&1` !~ /x86_64/
  STDERR.puts "\n\n"
  STDERR.puts "***************************************************************************************"
  STDERR.puts "********************* Only x86_64 linux is supported (for now) =( *********************"
  STDERR.puts "***************************************************************************************"
  exit(1)
end

dir_config('python')
unless have_header('python2.5/Python.h') or have_header('python2.6/Python.h') or have_header('python2.4/Python.h')
  STDERR.puts "\n\n"
  STDERR.puts "***************************************************************************************"
  STDERR.puts "***************** Python required (apt-get install python2.5-dev) =( ******************"
  STDERR.puts "***************************************************************************************"
  exit(1)
end

gdb = File.basename('gdb-7.0.tar.bz2')
dir = File.basename(gdb, '.tar.bz2')

puts "(I'm about to compile gdb7.. this will definitely take a while)"

Dir.chdir('src') do
  FileUtils.rm_rf(dir) if File.exists?(dir)

  sys("tar jxvf #{gdb}")
  Dir.chdir(dir+"/gdb") do
    if ENV['DEV']
      sys("git init")
      sys("git add .")
      sys("git commit -m 'initial source'")
    end

    %w[
      gdb-eval
      gdb-breakpoints
      gdb-leak
    ].each do |patch|
      sys("patch -p1 < ../../../../patches/#{patch}.patch")
      sys("git commit -am '#{patch}'") if ENV['DEV']
    end
  end

  Dir.chdir(dir) do
    sys("./configure --prefix=#{CWD}/dst/ --with-python=#{with_config('python-dir') || 'yes'}")
    sys("make")
    sys("make install")
  end
end

FileUtils.touch 'Makefile'
