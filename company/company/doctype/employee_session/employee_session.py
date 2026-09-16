import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds, flt

class EmployeeSession(Document):
	def validate(self):
		self.calculate_hours()

	def calculate_hours(self):
		total_work_seconds = 0
		now = frappe.utils.now_datetime()

		for d in self.intervals:
			# If interval is finished, enforce duration from times
			if d.from_time and d.to_time:
				# Ensure duration is not negative due to manual edit errors
				d.duration_seconds = max(0, time_diff_in_seconds(d.to_time, d.from_time))
			
			# If interval is active (no To Time), calculate snapshot duration up to Now/Last Seen
			# but allow manual override if duration_seconds is already set
			elif d.from_time and not d.to_time and not d.duration_seconds:
				ref_time = self.last_seen or now
				d.duration_seconds = max(0, time_diff_in_seconds(ref_time, d.from_time))

			# Count everything as work EXCEPT Offline, Break, and Away
			if d.status not in ('Offline', 'Break', 'Away'):
				total_work_seconds += flt(d.duration_seconds)

		# Convert total seconds to hours
		self.total_work_hours = flt(total_work_seconds / 3600.0, 3)
