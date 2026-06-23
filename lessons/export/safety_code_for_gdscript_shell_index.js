      // add the below to index.js in 
      // function _godot_js_eval
      
      // BEGIN: injected safety code
	  // window.parent.postMessage(%s, '*')
	  
	  const known_layout_pattern = /^window\.parent\.postMessage\((\{.*\}), ['](.*?)[']\);$/s;
	  const gShellPattern = /^window\.parent\.postMessage\(\{["]source["]:["]godot-activecode["],["]subject["]:["]runestone["],["]type["]:["]ready["]\}, ['][*][']\);$/s;
      const firstPostPattern = /^\s*if \(typeof window\.hostOrigin === [']undefined[']\) \{\n\s*window\.hostOrigin = null;\n\s*\}\n\s*\n\s*window\.addEventListener\('message', \(event\) => \{\n\s*if \(!window\.hostOrigin && event\.data && event\.data\.type === [']loadExercise[']\) \{\n\s*window\.hostOrigin = event\.origin;\n\s*}\n\s*\n\s*if \(event\.origin !== window\.hostOrigin\) return;\n\s*\n\s*if \(event\.data && event\.data\.type === [']loadExercise[']\) \{\n\s*if \(window\.godotLoadExerciseCallback\) \{\n\s*window\.godotLoadExerciseCallback\(event\.data\.payload\);\n\s*\}\n\s*\}\n\s+\}\);\n?\s*$/s
	  const printCapturePattern = /^\s*\(function\(\) \{\n\s+var _origLog = console\.log\.bind\(console\);\n\s+console\.log = function\(\) {\n\s+_origLog\.apply\(console, arguments\);\n\s+var text = Array\.prototype\.join\.call\(arguments, ['] [']\);\n\s+\n\s+var target = window\.hostOrigin \|\| ['][*]['];\n\s+\n\s+window\.parent\.postMessage\(\{\n\s+source:  [']godot-activecode['],\n\s+subject: [']runestone['],\n\s+type:    [']print['],\n\s+text:    text\s+\}, target\);\n\s+};\n\s+\}\)\(\);\n?\s*$/s
      const match = js_code.match(known_layout_pattern);
	  const is_godot_shell = js_code.match(gShellPattern);
	  const is_first_pattern = js_code.match(firstPostPattern);
	  const is_print_capture_pattern = js_code.match(printCapturePattern);
	  if (is_godot_shell || is_first_pattern || is_print_capture_pattern) {
		  // pass through
	  } else if (!match) {
		console.warn("Security Drop: java script not executed: ", js_code);
		return null;
	  } else {
		try {
            const target_origin = match[2];
            const allowed_targets = [
                "https://runestone.academy",
				"http://localhost:8129",
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
	 