import 'package:flutter/material.dart';

class AthleteScreen extends StatelessWidget {
  const AthleteScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Athletes'),
      ),
      body: const Center(
        child: Text('Athlete profiles coming soon'),
      ),
    );
  }
}
