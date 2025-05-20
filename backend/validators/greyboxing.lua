local lib = require("lib-greyboxing")
local inspect = require("inspect")

function just_in_backend(args, prompt, format)
	local search_in = lib.select_backends_for(args, format)

	lib.log{ args = args, prompt = prompt, format = format, search_in = search_in }

	local handler = args.handler

	local provider_id = args.host_data.studio_llm_id
	local model = lib.get_first_from_table(greyboxing.available_backends[provider_id].models).key

	prompt.use_max_completion_tokens = false

	for i = 1,3 do
		local success, result = pcall(function ()
			return lib.exec_in_backend(
				args.handler,
				{
					provider = provider_id,
					model = model,
					prompt = prompt,
					format = format,
				}
			)
		end)

		lib.log{level = "debug", message = "executed with", type = type(result), res = result}
		if success then
			return result
		elseif result.kind == "Overloaded" then
			-- nothing/continue
			lib.log{level = "warning", message = "service is overloaded", result = result}
		else
			lib.log{level = "error", message = "provider failed", result = result}

			error(result)
		end

		lib.log{level = "error", message = "sleeping before retry"}

		lib.sleep_seconds(1.5)
	end
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
