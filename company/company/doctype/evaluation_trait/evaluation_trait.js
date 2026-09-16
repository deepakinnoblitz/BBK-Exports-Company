frappe.ui.form.on('Evaluation Trait', {
	onload: function(frm) {
		if (frm.is_new() && (!frm.doc.evaluation_scores || frm.doc.evaluation_scores.length === 0)) {
			frappe.db.get_list('Evaluation Point', {
				fields: ['name', 'default_score']
			}).then(points => {
				points.forEach(point => {
					let row = frm.add_child('evaluation_scores');
					row.evaluation_point = point.name;
					row.score = point.default_score;
				});
				frm.refresh_field('evaluation_scores');
			});
		}
	}
});
