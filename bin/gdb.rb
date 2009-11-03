#!/usr/bin/env ruby
require 'rbconfig'

if ARGV.size == 1 and ARGV[0] =~ /^\d+$/
  ARGV.unshift "#{Config::CONFIG['bindir']}/ruby"
elsif ARGV.size == 2 and File.exist?(ARGV[0]) and ARGV[1] =~ /^\d+$/
else
  puts "Usage:"
  puts
  puts "  gdb.rb <pid>"
  puts "  gdb.rb <path to ruby> <pid>"
  puts
  exit(1)
end

cmd = "#{File.dirname(__FILE__)}/../ext/dst/bin/gdb -ex 'py execfile(\"#{File.dirname(__FILE__)}/../scripts/ruby-gdb.py\")' #{ARGV.join(" ")}"
exec(cmd)
