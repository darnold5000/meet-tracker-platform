class Meet {
  final int id;
  final String meetId;
  final String name;
  final String? location;
  final String? state;
  final DateTime? startDate;

  const Meet({
    required this.id,
    required this.meetId,
    required this.name,
    this.location,
    this.state,
    this.startDate,
  });

  factory Meet.fromJson(Map<String, dynamic> json) => Meet(
        id: json['id'] as int,
        meetId: json['meet_id'] as String,
        name: json['name'] as String,
        location: json['location'] as String?,
        state: json['state'] as String?,
        startDate: json['start_date'] != null
            ? DateTime.tryParse(json['start_date'] as String)
            : null,
      );
}

class Athlete {
  final int id;
  final String canonicalName;
  final String? gymName;
  final String? level;

  const Athlete({
    required this.id,
    required this.canonicalName,
    this.gymName,
    this.level,
  });

  factory Athlete.fromJson(Map<String, dynamic> json) => Athlete(
        id: json['id'] as int,
        canonicalName: json['canonical_name'] as String,
        gymName: json['gyms'] != null
            ? (json['gyms'] as Map<String, dynamic>)['canonical_name'] as String?
            : null,
        level: json['level'] as String?,
      );
}

class Score {
  final int id;
  final int meetId;
  final int athleteId;
  final String event;
  final String level;
  final double? score;
  final int? place;

  const Score({
    required this.id,
    required this.meetId,
    required this.athleteId,
    required this.event,
    required this.level,
    this.score,
    this.place,
  });

  factory Score.fromJson(Map<String, dynamic> json) => Score(
        id: json['id'] as int,
        meetId: json['meet_id'] as int,
        athleteId: json['athlete_id'] as int,
        event: json['event'] as String,
        level: json['level'] as String,
        score: (json['score'] as num?)?.toDouble(),
        place: json['place'] as int?,
      );
}
