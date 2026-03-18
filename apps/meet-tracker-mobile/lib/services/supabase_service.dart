import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/models.dart';

class SupabaseService {
  static final _client = Supabase.instance.client;

  static Future<List<Meet>> getMeets() async {
    final data = await _client
        .from('meets')
        .select('id, meet_id, name, location, state, start_date')
        .order('start_date', ascending: false);
    return (data as List).map((e) => Meet.fromJson(e)).toList();
  }

  static Future<List<Athlete>> searchAthletes(String query) async {
    final data = await _client
        .from('athletes')
        .select('id, canonical_name, level, gyms(canonical_name)')
        .ilike('canonical_name', '%$query%')
        .limit(50);
    return (data as List).map((e) => Athlete.fromJson(e)).toList();
  }

  static Future<List<Score>> getAthleteScores(int athleteId) async {
    final data = await _client
        .from('scores')
        .select('id, meet_id, athlete_id, event, level, score, place')
        .eq('athlete_id', athleteId)
        .order('meet_id');
    return (data as List).map((e) => Score.fromJson(e)).toList();
  }

  static Future<List<Map<String, dynamic>>> getRankings({
    required String level,
    required String event,
    String? state,
  }) async {
    var query = _client
        .from('scores')
        .select('score, place, level, athletes(canonical_name, gyms(canonical_name)), meets(name, start_date, state)')
        .eq('event', event)
        .eq('level', level)
        .not('score', 'is', null)
        .order('score', ascending: false)
        .limit(100);

    final data = await query;
    return (data as List).cast<Map<String, dynamic>>();
  }
}
