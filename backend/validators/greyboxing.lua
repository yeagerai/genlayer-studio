local lib = require("lib-greyboxing")
local inspect = require("inspect")

function just_in_backend(args, prompt, format)
	local handler = args.handler

	local provider_id = args.host_data.studio_llm_id
	local model = lib.get_first_from_table(greyboxing.available_backends[provider_id].models).key

	lib.log{ args = args, prompt = prompt, format = format, provider_id = provider_id, model = model }

	return handler:exec_in_backend({
		provider = provider_id,
		model = model,
		prompt = prompt,
		format = format,
	})
end

function exec_prompt(args)
	local handler = args.handler

	local mapped = lib.exec_prompt_transform(args)

	return just_in_backend(args, mapped.prompt, mapped.format)
end

function exec_prompt_template(args)
	local handler = args.handler

	local mapped = lib.exec_prompt_template_transform(args)

	return just_in_backend(args, mapped.prompt, mapped.format)
end
