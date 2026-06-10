extends "res://addons/gdpractice/tester/test.gd"


func _build_checks() -> void:
	var practice_slot = _practice

	var c1 := Check.new()
	c1.description = "Function add_numbers() exists"
	c1.checker = func() -> String:
		if practice_slot.has_method("add_numbers"):
			return ""
		return "Define a function called add_numbers(a, b) in your code."

	var c2 := Check.new()
	c2.description = "add_numbers(2, 3) returns 5"
	c2.checker = func() -> String:
		if not practice_slot.has_method("add_numbers"):
			return "Define add_numbers(a, b) first."
		if practice_slot.add_numbers(2, 3) == 5:
			return ""
		return "Your function should return the sum of the two arguments."
	c2.dependencies.push_back(c1)

	checks.append_array([c1, c2])
