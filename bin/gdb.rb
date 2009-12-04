#!/usr/bin/env ruby
require 'rbconfig'

if ARGV.size == 1 && ARGV[0] =~ /^\d+$/
  pid = ARGV[0]
elsif ARGV.size == 1 && ARGV[0] == 'none'
  pid = nil
else
  puts "Usage:"
  puts
  puts "  gdb.rb <pid>"
  puts
  exit(1)
end

dir = File.expand_path(File.join(File.dirname(__FILE__), '..'))

args = []
args << "#{dir}/ext/dst/bin/gdb"
args << "-ex 'py execfile(\"#{dir}/scripts/ruby-gdb.py\")'"
if pid
  args << "-ex 'attach #{pid}'"
else
  args << "#{Config::CONFIG['bindir']}/#{Config::CONFIG['ruby_install_name']}"
end

exec(args.join(' '))
