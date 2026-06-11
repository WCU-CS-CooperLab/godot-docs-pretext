      // add the below to index.js in 
      // function _godot_js_eval
      
      // BEGIN: injected safety code
	  // window.parent.postMessage(%s, '*')
	  
	  const known_layout_pattern = /^window\.parent\.postMessage\((\{.*\}), ['](.*?)[']\);$/s;
	  const gShellPattern = /^window.godotShell = {};$/s;
      const firstPostPattern = /^window\.parent\.postMessage\(\{"source":"godot-activecode","subject":"runestone","type":"ready"\}, ['][*][']\);/s
	  const match = js_code.match(known_layout_pattern);
	  const is_godot_shell = js_code.match(gShellPattern);
	  const is_first_pattern = js_code.match(firstPostPattern);
	  if (is_godot_shell || is_first_pattern) {
		  // pass through
	  } else if (!match) {
		console.warn("Security Drop: java script not executed: ", js_code);
		return null;
	  } else {
		try {
            const target_origin = match[2];
            const allowed_targets = [
                "https://runestone.academy",
                window.location.origin,
            ];
            if (!allowed_targets.includes(target_origin)) {
                console.warn("Security Drop: java script not executed because", 
					         "target is not allowed ", js_code);
				return null;
            }
			const expected_json = JSON.parse(match[1]);
			const is_dictionary = (typeof expected_json === 'object' 
			                       && expected_json !== null 
								   && !Array.isArray(expected_json));
			if (!is_dictionary) {
				console.warn("Security Drop: java script not executed because", 
					         "first argument is not a JSON Dictionary: ", js_code);
				return null;
	  		 
			}
							 
		} catch (json_error) {
			console.warn("Security Drop: java script not executed: (bad JSON) ", js_code);
			return null;
		}
	  }
	
	  // passed tests. most likely safe to run javascript
	  // END: injected safety code
	 