# 加载 .env 文件
ifneq (,$(wildcard .env))
    include .env
    export
endif

K6_BIN ?= ../../_output/bin/k6

.PHONY: python
python:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.sympy_1776_sympy-16450:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="python -m pip install -e ." \
	  -e TEST_COMMAND="bin/test -C --verbose" \
	  -e EXEC_OPTIONS='{"env":{"PYTHONWARNINGS":"ignore::UserWarning,ignore::SyntaxWarning"},"workdir":"/testbed"}'

.PHONY: c
c:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.redis_1776_redis-13115:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="make" \
	  -e TEST_COMMAND="./runtest --durable --single unit/scripting" \
	  -e EXEC_OPTIONS='{"env":{"TERM":"dumb"},"workdir":"/testbed"}'

.PHONY: go
go:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.caddyserver_1776_caddy-6411:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="go mod tidy" \
	  -e TEST_COMMAND="go test -v . -run "TestReplacerNew*"" \
	  -e EXEC_OPTIONS='{"env":{},"workdir":"/testbed"}'

.PHONY: java
java:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.google_1776_gson-2158:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="mvn clean install -B -pl gson -DskipTests -am" \
	  -e TEST_COMMAND='["mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testByteSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testShortSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testIntSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testLongSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testFloatSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testDoubleSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testPrimitiveIntegerAutoboxedSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testPrimitiveIntegerAutoboxedInASingleElementArraySerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testReallyLongValuesSerialization","mvnd test -B -pl gson -Dtest=com.google.gson.functional.PrimitiveTest#testPrimitiveLongAutoboxedSerialization"]' \
	  -e EXEC_OPTIONS='{"env":{},"workdir":"/testbed"}'

.PHONY: javascript
javascript:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.markedjs_1776_marked-1825:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="npm install" \
	  -e TEST_COMMAND="./node_modules/.bin/jasmine --no-color --config=jasmine.json" \
	  -e EXEC_OPTIONS='{"env":{},"workdir":"/testbed"}'

.PHONY: php
php:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.phpoffice_1776_phpspreadsheet-4214:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND='["composer update", "composer install"]' \
	  -e TEST_COMMAND="./vendor/bin/phpunit --testdox --colors=never tests/PhpSpreadsheetTests/Reader/Ods/FormulaTranslatorTest.php" \
	  -e EXEC_OPTIONS='{"env":{},"workdir":"/testbed"}'

.PHONY: ruby
ruby:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.jekyll_1776_jekyll-9141:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="script/bootstrap" \
	  -e TEST_COMMAND='bundle exec ruby -I test test/test_site.rb -v -n "/static files/"' \
	  -e EXEC_OPTIONS='{"env":{},"workdir":"/testbed"}'

.PHONY: rust
rust:
	$(K6_BIN) run ./script.js \
	  -e IMAGE="ccr.ccs.tencentyun.com/finofliu/sweb.eval.x86_64.burntsushi_1776_ripgrep-2576:latest" \
	  -e IMAGE_REGISTRY_TYPE="personal" \
	  -e INSTALL_COMMAND="cargo test --package ripgrep --test integration --no-run" \
	  -e TEST_COMMAND="cargo test --package ripgrep --test integration -- regression" \
	  -e EXEC_OPTIONS='{"env":{"RUSTFLAGS":"-Awarnings"},"workdir":"/testbed"}'
